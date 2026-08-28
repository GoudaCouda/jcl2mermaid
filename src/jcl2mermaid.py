from typing import Optional, Sequence,List
import re
from models import JclJob, JclStep, DDStatement, Dataset


def preprocess_lines(lines: Sequence[str],args) -> List[str]:
    logical_statements: List[str] = []

    for line in lines:
        clean = line.rstrip()
        if not clean or clean.startswith("/*"):
            continue

        if clean.startswith("//*"):
            if args.include_comments:
            # Check that the comment contains at least one alphabetic character
            # (Filters out lines like '//*', '//* ====', '//* --------', '//* 123456')
                if re.search(r"[a-zA-Z]", clean[3:]):
                    logical_statements.append(clean)
            continue

        # If it's a continuation (starts with '// '), attach to the last non-comment statement
        if clean.startswith("// "):
            for idx in range(len(logical_statements) - 1, -1, -1):
                if not logical_statements[idx].startswith("//*"):
                    logical_statements[idx] += " " + clean[3:].strip()
                    break
            continue

        # New statement / SYSIN data card
        logical_statements.append(clean)

    return logical_statements

def sanitize_id(text: str) -> str:
    # Replaces all non-alphanumeric characters (spaces, dots, +, -, parens) with underscores
    return re.sub(r'[^a-zA-Z0-9_]', '_', text)



def extract_dataset_info(dd_name: str, params: str) -> tuple[str, str] | None:
    """
    Extracts (dsn_or_type, disp) from DD parameters.
    """
    datasets = []
    params_upper = params.upper().strip()

        
    #  (//SYSIN DD DUMMY or DSN=NULLFILE)
    if params_upper.startswith("DUMMY") or "DSN=NULLFILE" in params_upper:
        return []

        
    # //SYSPRINT DD SYSOUT=*
    sysout_match = re.search(r"SYSOUT=([^,\s]+)", params, re.IGNORECASE)
    if sysout_match:
        #not gonna get these for now
        #return (f"SYSOUT({sysout_match.group(1)})", "OUTPUT")
        return []
    
    # 4. Standard DSN

    # Split on whitespace + 'DD ' to isolate each concatenated dataset segment
    segments = re.split(r"\s+DD\s+", params.strip(), flags=re.IGNORECASE)
    
    for segment in segments:
        if not segment.strip():
            continue
        dsn_match = re.search(r"(?:DSN|DSNAME)=([^,\s]+)", segment, re.IGNORECASE)
        disp_match = re.search(r"DISP=(\([^)]+\)|[^,\s]+)", segment, re.IGNORECASE)   
        if dsn_match:
            dsn = dsn_match.group(1).strip("'\"")
            disp = disp_match.group(1) if disp_match else "SHR"
            datasets.append(Dataset(dsn=dsn, disp=disp))
    return datasets
        

def is_output_disp(disp):
    """
    Checks JCL to see if it is an input or output and returns true for output and false for input
    """

    
    clean_disp = re.sub(r"[()]","",disp) 
    status_disp,normal_disp,abnormal_disp = (clean_disp.split(",") + ["", "", ""])[:3]
    # set up for if any disp are mising in the statement
    if not status_disp:
        status_disp = "NEW"
    if status_disp == "NEW" and not normal_disp:
        normal_disp = "DELETE"

    # start checking if its input or output
    if normal_disp in ("DELETE", "UNCATLG"):
        if status_disp == "NEW":
            return "SCRATCH"  # Created and deleted in the same step (e.g. SORTWK)
        return "DELETE"
    if status_disp in ("NEW", "MOD"):
        return "OUTPUT"
    return "INPUT"

def parse_statements(statements: List[str],args) -> JclJob:
    job = JclJob(name="Unknown Job")
    current_step: JclStep | None = None
    pending_comments: List[str] = []
    current_dd: Optional[DDStatement] = None
    for stmt in statements:


        # 1. Handle Comments
        if stmt.startswith("//*"):
            if args.include_comments:
                pending_comments.append(stmt[3:].strip())
            continue

        if stmt.startswith("/*"):
            # Close the active in-stream DD payload
            current_dd = None
            continue

        if not stmt.startswith("//"):
            if current_dd is not None:
                current_dd.cards.append(stmt.strip())
            continue


        # matching jcl structure to our dataclass
        # matches 3 patterns //LABEL OPERATION PARAMS 
        match = re.match(r"^//([A-Z0-9#@$]+)?\s+([A-Z]+)\s*(.*)$", stmt, re.IGNORECASE)

        if not match:
            continue

        label,operation,params = match.groups()
        label = label or ""
        operation = operation.upper()
        if operation == "JOB":
            job.name = label
            job.comments.extend(pending_comments)
            pending_comments.clear()
        elif operation == "EXEC":
            # Extract program name (PGM=xxx) or procedure name (PROC=xxx or direct name)
            pgm_match = re.search(r"(?:PGM|PROC)=([A-Z0-9#@$]+)", params, re.IGNORECASE)
            # grabs the program name if regex finds it. or if shorthand is used it defaults to the proc name. ex //STEP1 EXEC MYPROC instead of //STEP1 EXEC PROC=MYPROC
            program_name = pgm_match.group(1) if pgm_match else params.split(",")[0].strip() 


            current_step=JclStep(name=label, program=program_name)
            current_step.comments.extend(pending_comments)
            pending_comments.clear()
            job.steps.append(current_step)

        elif operation == "DD":
            # Extract DSN and DISP 
            if pending_comments:
                if current_step is not None:
                    current_step.comments.extend(pending_comments)
                else:
                    job.comments.extend(pending_comments)
                pending_comments.clear()
    

            
            parsed_datasets = extract_dataset_info(label, params) or []

            if label.upper() == "STEPLIB" and current_step is not None:
                current_step.steplib.extend([d.dsn for d in parsed_datasets if d.dsn])
                current_dd = None
                continue

            if label.upper() == "JOBLIB":
                job.joblib.extend([d.dsn for d in parsed_datasets if d.dsn])
                current_dd = None
                continue

            
            dd_stmt = DDStatement(
                name=label, raw_block=stmt, datasets=parsed_datasets
            )

            if current_step is not None:
                current_step.dds.append(dd_stmt)
            else:
                job.global_dds.append(dd_stmt)

            # Set as active DD so subsequent non-'//' card lines append here
            current_dd = dd_stmt

    if pending_comments:
        if current_step:
            current_step.comments.extend(pending_comments)
        else:
            job.comments.extend(pending_comments)
    return job



def format_cards(cards: list[str]) -> str:
    cleaned = [c.strip() for c in cards if c.strip()]
    if not cleaned:
        return ""

    # If all lines are very short (e.g., 1-2 words / <= 20 chars), join inline with spaces
    if len(cleaned) <= 6 and all(len(line) <= 20 for line in cleaned):
        return " ".join(cleaned)

    # Otherwise preserve multiline structure
    return "".join(cleaned)


def design_mermaid(job: JclJob) -> str:
    mermaid_lines = [
        '%%{init: { "flowchart": { "defaultRenderer": "elk", "nodeSpacing": 25, "rankSpacing": 35 } }}%%',
        'flowchart TD',
        f'  %% Job: {job.name}',
        '  classDef stepCard fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a,text-align:left;',
        '  classDef handoffCard fill:#ecfdf5,stroke:#059669,stroke-dasharray: 0,stroke-width:1.5px,color:#064e3b,font-size:12px;',
        '  linkStyle default stroke:#64748b,stroke-width:1.5px;',
        ''
    ]

    handoff_nodes = {}
    step_sequence_edges = []
    data_edges = []
    step_ids = []
    for step_idx,step in enumerate(job.steps):
        step_num = f"{step_idx + 1:02d}"
        step_id = f"Step{step_idx+1}_{sanitize_id(step.name)}"
        step_ids.append(step_id)
        reads = []
        deletes = []
        sysin_cards = []

    # Process DD datasets and determine input/output flow
        for dd in step.dds:
            for ds in dd.datasets:
                disp_upper = (ds.disp or "").upper()
                raw_dsn = ds.dsn or ""
                clean_dsn = raw_dsn.replace('"', '').replace("'", "")
                if not clean_dsn:
                    continue
                            
                # Check if it's an output (, implies its new)
                filetype = is_output_disp(disp_upper)



                ds_id = f"ds_{sanitize_id(clean_dsn)}"
                edge_label_safe = ds.disp.replace('"', "'") if ds.disp else ""
                edge_label_str = f'|"{edge_label_safe}"|' if edge_label_safe else ""

                if filetype == "OUTPUT":
                    disp_part = f"<br/><sub style='font-weight:normal;'>DISP: {edge_label_safe}</sub>" if edge_label_safe else ""
                    handoff_nodes[ds_id] = f"<b>{dd.name}:</b> {clean_dsn}{disp_part}"
                    data_edges.append(f"  {step_id} --> {ds_id}")  
                elif ds_id in handoff_nodes:
                    # An earlier step created this file -> Draw pipeline handoff arrow
                    # (This catches &&TEMPRAW in Step 3 cleanly without cluttering the step box)
                    data_edges.append(f"  {ds_id} --> {step_id}")
                elif filetype == "DELETE":
                    # Standalone cleanup step (e.g. IEFBR14 in Step 1)
                    prefix = f"<b>{dd.name}:</b> " if dd.name else ""
                    deletes.append(f"<span style='white-space:nowrap; color:red;'>{prefix}{clean_dsn}</span>")

                elif filetype == "SCRATCH":
                    # Intra-step scratch file (SORTWK, etc.) -> Ignore completely
                    pass

                else:
                    # Static/read-only lookup -> Keep inline
                    prefix = f"<b>{dd.name}:</b> " if dd.name else ""
                    reads.append(f"<span style='white-space:nowrap; font-size:11px;'>{prefix}{clean_dsn}</span>")
        

        label_parts = [f"<b>{step.name}</b><br/><sub style='color:#4338ca !important; fill:#4338ca !important; font-weight:bold; font-size:12px;'>[ PGM: {step.program} ]</sub>"]


        details = []

        instream_cards = [
            f"<font color='#0284c7'><b>{dd.name.upper()}:</b></font><br/>"
            f"<tt style='font-size:11px; line-height:1.15; display:block;'>{format_cards(dd.cards)}</tt>"
            for dd in step.dds
            if getattr(dd, "cards", None) and any(c.strip() for c in dd.cards)
        ]
        if instream_cards:
            # Inserts all in-stream DD blocks (SYSIN, SORTCNTL, etc.) directly into details
            details.extend(instream_cards)

        if step.steplib:
            lib_display = ", ".join(step.steplib)
            label_parts.append(f"<br/><sub style='color:#64748b;'>LIB: {lib_display}</sub>")
        if reads:
            details.append(f"<font color='#059669'><b>External Input:</b></font><br/>{('<br/>').join(reads)}")
        if deletes:
            details.append(f"<font color='#dc2626'><b>Deletes:</b></font><br/>{('<br/>').join(deletes)}")
        if details:
            label_parts.append("<hr/>" + "".join(details))
        if step.comments:
            label_parts.append("<hr/>")
            clean_comments = [
                f"• {c.lstrip('/*=- ').strip().replace('\"', '\'').replace('[', '(').replace(']', ')')}"
                for c in step.comments
                if c.strip()
            ]
            if clean_comments:
                comments_text = "<br/>".join(clean_comments)
                label_parts.append(
                    f"<div align='left'><font color='#64748b' size='1'><i>{comments_text}</i></font></div>"
                )

        step_label = f"<div align='left'>{''.join(label_parts)}</div>"
        mermaid_lines.append(f'  {step_id}["{step_label}"]:::stepCard') 

    if handoff_nodes:
        mermaid_lines.append("")
        for ds_id, dsn in handoff_nodes.items():
            mermaid_lines.append(f'  {ds_id}(["{dsn}"]):::handoffCard')


    # Append all dataset <-> step connection lines
    if len(step_ids) > 1:
        for idx in range(len(step_ids) - 1):
            mermaid_lines.append(f"  {step_ids[idx]} -.-> {step_ids[idx+1]}")

    # 3. Append dataset dataflow connections
    if data_edges:
        mermaid_lines.append("")
        mermaid_lines.extend(data_edges)

        
    return "\n".join(mermaid_lines)


def escape_dot_text(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def design_graphviz(job: JclJob) -> str:
    dot_lines = [
        f'// Job: {job.name}',
        'digraph JCL_Flow {',
        '  graph [',
        '    rankdir=TB,',
        '    bgcolor="transparent",',
        '    nodesep=0.4,',
        '    ranksep=0.6,',
        '    pad=0.3,',
        '    fontname="Segoe UI, -apple-system, Helvetica, Arial, sans-serif"',
        '  ];',
        '  node [',
        '    fontname="Segoe UI, -apple-system, Helvetica, Arial, sans-serif",',
        '    fontsize=10,',
        '    shape=none,',
        '    margin=0',
        '  ];',
        '  edge [',
        '    fontname="Segoe UI, -apple-system, Helvetica, Arial, sans-serif",',
        '    fontsize=9,',
        '    color="#64748b",',
        '    penwidth=1.5',
        '  ];',
        ''
    ]

    handoff_nodes = {}
    data_edges = []
    step_ids = []

    for step_idx, step in enumerate(job.steps):
        step_id = f"Step{step_idx+1}_{sanitize_id(step.name)}"
        step_ids.append(step_id)
        reads = []
        deletes = []

        # Process DD datasets and determine input/output flow
        for dd in step.dds:
            for ds in dd.datasets:
                disp_upper = (ds.disp or "").upper()
                raw_dsn = ds.dsn or ""
                clean_dsn = raw_dsn.replace('"', '').replace("'", "")
                if not clean_dsn:
                    continue

                filetype = is_output_disp(disp_upper)
                ds_id = f"ds_{sanitize_id(clean_dsn)}"
                edge_label_safe = ds.disp.replace('"', "'") if ds.disp else ""

                if filetype == "OUTPUT":
                    handoff_nodes[ds_id] = (escape_dot_text(dd.name), escape_dot_text(clean_dsn), escape_dot_text(edge_label_safe))
                    data_edges.append(f"  {step_id} -> {ds_id};")
                elif ds_id in handoff_nodes:
                    data_edges.append(f"  {ds_id} -> {step_id};")
                elif filetype == "DELETE":
                    prefix = f"<B>{escape_dot_text(dd.name)}:</B> " if dd.name else ""
                    deletes.append(f"{prefix}{escape_dot_text(clean_dsn)}")
                elif filetype == "SCRATCH":
                    pass
                else:
                    prefix = f"<B>{escape_dot_text(dd.name)}:</B> " if dd.name else ""
                    reads.append(f"{prefix}{escape_dot_text(clean_dsn)}")

        # Build Step Card HTML Table
        table_rows = []
        
        # Header: Step name + Program name
        escaped_step_name = escape_dot_text(step.name)
        escaped_pgm = escape_dot_text(step.program)
        table_rows.append(
            f'<TR><TD ALIGN="LEFT"><B><FONT COLOR="#0f172a" POINT-SIZE="12">{escaped_step_name}</FONT></B></TD></TR>'
        )
        table_rows.append(
            f'<TR><TD ALIGN="LEFT"><B><FONT COLOR="#4338ca" POINT-SIZE="9">[ PGM: {escaped_pgm} ]</FONT></B></TD></TR>'
        )

        if step.steplib:
            lib_display = escape_dot_text(", ".join(step.steplib))
            table_rows.append(
                f'<TR><TD ALIGN="LEFT"><FONT COLOR="#64748b" POINT-SIZE="9">LIB: {lib_display}</FONT></TD></TR>'
            )

        # In-stream DD cards (SYSIN, etc.)
        instream_cards = [
            (escape_dot_text(dd.name.upper()), escape_dot_text(format_cards(dd.cards)))
            for dd in step.dds
            if getattr(dd, "cards", None) and any(c.strip() for c in dd.cards)
        ]

        has_details = instream_cards or reads or deletes

        if has_details:
            table_rows.append('<HR/>')

        for dd_name_esc, card_content in instream_cards:
            table_rows.append(
                f'<TR><TD ALIGN="LEFT"><B><FONT COLOR="#0284c7" POINT-SIZE="9">{dd_name_esc}:</FONT></B></TD></TR>'
            )
            table_rows.append(
                f'<TR><TD ALIGN="LEFT"><FONT FACE="Courier New, monospace" POINT-SIZE="8" COLOR="#334155">{card_content}</FONT></TD></TR>'
            )

        if reads:
            table_rows.append(
                '<TR><TD ALIGN="LEFT"><B><FONT COLOR="#059669" POINT-SIZE="9">External Input:</FONT></B></TD></TR>'
            )
            for r in reads:
                table_rows.append(
                    f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="8" COLOR="#334155">{r}</FONT></TD></TR>'
                )

        if deletes:
            table_rows.append(
                '<TR><TD ALIGN="LEFT"><B><FONT COLOR="#dc2626" POINT-SIZE="9">Deletes:</FONT></B></TD></TR>'
            )
            for d in deletes:
                table_rows.append(
                    f'<TR><TD ALIGN="LEFT"><FONT POINT-SIZE="8" COLOR="#dc2626">{d}</FONT></TD></TR>'
                )

        if step.comments:
            clean_comments = [
                escape_dot_text(c.lstrip('/*=- ').strip().replace('"', '\'').replace('[', '(').replace(']', ')'))
                for c in step.comments
                if c.strip()
            ]
            if clean_comments:
                table_rows.append('<HR/>')
                for c in clean_comments:
                    table_rows.append(
                        f'<TR><TD ALIGN="LEFT"><I><FONT POINT-SIZE="8" COLOR="#64748b">&#8226; {c}</FONT></I></TD></TR>'
                    )

        table_content = "\n        ".join(table_rows)
        dot_lines.append(f'  {step_id} [label=<\n    <TABLE BORDER="1" COLOR="#64748b" CELLBORDER="0" CELLSPACING="0" CELLPADDING="7" BGCOLOR="#f8fafc" STYLE="ROUNDED">\n        {table_content}\n    </TABLE>\n  >];\n')

    # Handoff nodes
    if handoff_nodes:
        for ds_id, (dd_name_esc, clean_dsn_esc, disp_esc) in handoff_nodes.items():
            disp_row = f'\n        <TR><TD ALIGN="CENTER"><FONT POINT-SIZE="8" COLOR="#059669">DISP: {disp_esc}</FONT></TD></TR>' if disp_esc else ""
            dot_lines.append(
                f'  {ds_id} [label=<\n'
                f'    <TABLE BORDER="1" COLOR="#059669" CELLBORDER="0" CELLSPACING="0" CELLPADDING="6" BGCOLOR="#ecfdf5" STYLE="ROUNDED">\n'
                f'        <TR><TD ALIGN="CENTER"><B><FONT POINT-SIZE="9" COLOR="#064e3b">{dd_name_esc}: {clean_dsn_esc}</FONT></B></TD></TR>{disp_row}\n'
                f'    </TABLE>\n'
                f'  >];'
            )
        dot_lines.append('')

    # Step sequence connections (dashed)
    if len(step_ids) > 1:
        for idx in range(len(step_ids) - 1):
            dot_lines.append(f'  {step_ids[idx]} -> {step_ids[idx+1]} [style=dashed, color="#64748b"];')
        dot_lines.append('')

    # Data flow connections
    if data_edges:
        dot_lines.extend(data_edges)
        dot_lines.append('')

    dot_lines.append('}')
    return "\n".join(dot_lines)


def process_diagram(lines: Sequence[str], args) -> str:
    logical_statements = preprocess_lines(lines, args)
    jclJob = parse_statements(logical_statements, args)
    
    designtype = str(getattr(args, "designtype", None) or getattr(args, "format", "mermaid")).lower()
    if designtype in ["graphviz", "dot"]:
        output_diagram = design_graphviz(jclJob)
    else:
        output_diagram = design_mermaid(jclJob)
    
    return output_diagram


if __name__ == "__main__":
    main()