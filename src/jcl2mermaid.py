from typing import Sequence,List
import re
from models import JclJob, JclStep, DDStatement, Dataset


def preprocess_lines(lines: Sequence[str]) -> str:
    logical_statements = []
    current_statement = ""
    for line in lines:
        clean_line = line.rstrip()

        is_new_statement = len(clean_line) > 2 and clean_line.startswith("//") and clean_line[2] != ' '

        if clean_line.startswith(("//*","/*")):
            continue
        if is_new_statement:
            if current_statement:
                logical_statements.append(current_statement)
            current_statement = clean_line
        else:
            current_statement += " " + clean_line.lstrip("/ ")
    if current_statement:
        logical_statements.append(current_statement)
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
    
    # In-stream Data (//SYSIN DD * or DD DATA)
    if params_upper.startswith("*") or params_upper.startswith("DATA"):
        params_clean = params.strip()
        params_upper = params_clean.upper()

        cmd_text = re.sub(r"^(\*|DATA)\s*", "", params_clean, flags=re.IGNORECASE).strip()
        if cmd_text:
            return [Dataset(dsn="IN-STREAM DATA", disp="INPUT",content=cmd_text)]
        return []

        
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

def parse_statements(statements: List[str]) -> JclJob:
    job = JclJob(name="Unknown Job")
    current_step: JclStep | None = None

    for stmt in statements:
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
        elif operation == "EXEC":
            # Extract program name (PGM=xxx) or procedure name (PROC=xxx or direct name)
            pgm_match = re.search(r"(?:PGM|PROC)=([A-Z0-9#@$]+)", params, re.IGNORECASE)
            # grabs the program name if regex finds it. or if shorthand is used it defaults to the proc name. ex //STEP1 EXEC MYPROC instead of //STEP1 EXEC PROC=MYPROC
            program_name = pgm_match.group(1) if pgm_match else params.split(",")[0].strip() 


            current_step=JclStep(name=label, program=program_name)
            job.steps.append(current_step)

        elif operation == "DD":
            # Extract DSN and DISP 
            
    
            # Skip standard diagnostic print logs to keep diagrams readable
            #if label.upper() in [ "SYSPRINT", "SYSUDUMP", "CEEDUMP"]:
            #    continue

            parsed_datasets = extract_dataset_info(label, params)
            if not parsed_datasets:
                continue
            if label.upper() == "STEPLIB" and current_step is not None:
                current_step.steplib.extend([d.dsn for d in parsed_datasets if d.dsn])
                continue

            if label.upper() == "JOBLIB":
                job.joblib.extend([d.dsn for d in parsed_datasets if d.dsn])
                continue
        
            dd_stmt = DDStatement(
                name=label,
                raw_block=stmt,
                datasets=parsed_datasets
            )
            # if not none it means its concantinated with other dd's
            if current_step is not None:
                current_step.dds.append(dd_stmt)
            else:
                # Save as a global/job-level DD. most likely in the form of a job lib statement
                job.global_dds.append(dd_stmt)
    return job

def design_diagram(job: JclJob) -> str:
    mermaid_lines = [
        '%%{init: { "flowchart": { "defaultRenderer": "elk", "nodeSpacing": 25, "rankSpacing": 35 } }}%%',
        'flowchart TD',
        f'  %% Job: {job.name}',
        '  classDef stepCard fill:#f8fafc,stroke:#64748b,stroke-width:1.5px,color:#0f172a,text-align:left;',
        '  classDef handoffCard fill:#ecfeff,stroke:#0284c7,stroke-width:1.5px,color:#0369a1,font-weight:bold;',
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


                if clean_dsn == "IN-STREAM DATA" or dd.name.upper() == "SYSIN":
                    card_text = getattr(ds, "content", "").strip()
                    if card_text:
                        sysin_cards.append(card_text)
                    continue
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
                    reads.append(f"<span style='white-space:nowrap;'>{prefix}{clean_dsn}</span>")
        

        label_parts = [f"<b>{step.name}</b><br/><sub style='color:#4338ca !important; fill:#4338ca !important; font-weight:bold; font-size:12px;'>[ PGM: {step.program} ]</sub>"]


        details = []
        if step.steplib:
            lib_display = ", ".join(step.steplib)
            label_parts.append(f"<br/><sub style='color:#64748b;'>LIB: {lib_display}</sub>")
        if sysin_cards:
            details.append(f"<i>SYSIN:</i> {', '.join(sysin_cards)}")
        if reads:
            details.append(f"<i>Reads:</i> {',\n'.join(reads)}")
        if deletes:
            details.append(f"<i>Deletes:</i> {', '.join(deletes)}")
        if details:
            label_parts.append("<hr/>" + "<br/>".join(details))

        step_label = "".join(label_parts)
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
    


def process_diagram(lines: Sequence[str]) -> str:
    logical_statements = preprocess_lines(lines)
    jclJob = parse_statements(logical_statements)
    output_diagram = design_diagram(jclJob)
    
    return output_diagram


if __name__ == "__main__":
    main()