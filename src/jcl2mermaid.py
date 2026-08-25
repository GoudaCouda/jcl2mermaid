from typing import Sequence,List
import re
from models import JclJob, JclStep, DDStatement, Dataset


def preprocess_lines(lines: Sequence[str]) -> str:
    logical_statements = []
    current_statement = ""
    for line in lines:
        clean_line = line.rstrip()

        is_new_statement = len(clean_line) > 2 and clean_line.startswith("//") and clean_line[2] != ' '

        if clean_line.startswith("//*"):
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
    params_upper = params.upper().strip()
    
    # In-stream Data (//SYSIN DD * or DD DATA)
    if params_upper.startswith("*") or params_upper.startswith("DATA"):
        return ("IN-STREAM DATA", "INPUT")
        
    #  (//SYSIN DD DUMMY or DSN=NULLFILE)
    if params_upper.startswith("DUMMY") or "DSN=NULLFILE" in params_upper:
        return None

        
    # //SYSPRINT DD SYSOUT=*
    sysout_match = re.search(r"SYSOUT=([^,\s]+)", params, re.IGNORECASE)
    if sysout_match:
        # not going to capture it for now
        #return (f"SYSOUT({sysout_match.group(1)})", "OUTPUT")
        return None
    # 4. Standard DSN
    dsn_match = re.search(r"(?:DSN|DSNAME)=([^,\s]+)", params, re.IGNORECASE)
    disp_match = re.search(r"DISP=(\([^)]+\)|[^,\s]+)", params, re.IGNORECASE)    
    if dsn_match:
        dsn = dsn_match.group(1).strip("'\"")
        disp = disp_match.group(1) if disp_match else "SHR"
        return (dsn, disp)
        
    return None



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
            if label.upper() in ["SYSOUT", "SYSPRINT", "SYSUDUMP", "CEEDUMP"]:
                continue

            info = extract_dataset_info(label, params)
            if not info:
                continue

            dsn, disp = info
            dd_stmt = DDStatement(
                name=label,
                raw_block=stmt,
                datasets=[Dataset(dsn=dsn, disp=disp)]
            )
            # if not none it means its concantinated with other dd's
            if current_step is not None:
                current_step.dds.append(dd_stmt)
            else:
                # Save as a global/job-level DD. most likely in the form of a job lib statement
                job.global_dds.append(dd_stmt)
    return job

def design_diagram(job: JclJob) -> str:
    mermaid_lines = ["flowchart TD"]    
    mermaid_lines.append(f"  %% Job: {job.name}")

    step_sequence_edges = []

    for step_idx,step in enumerate(job.steps):
        step_id = f"Step{step_idx+1}_{sanitize_id(step.name)}"
        mermaid_lines.append(f"subgraph sub_{step_id} [Step:{step.name}]")
        mermaid_lines.append(f'    {step_id}["<b>{step.name}</b><br/>PGM: {step.program}"]')


    # Process DD datasets and determine input/output flow
        for dd in step.dds:
            for ds in dd.datasets:

                if ds.dsn == "IN-STREAM DATA":
                    ds_id = f"ds_SYSIN_{step_id}"
                    ds_label = f'{ds_id}[("<b>{dd.name}</b><br/>IN-STREAM DATA")]'
                else:
                    ds_id = f"ds_{sanitize_id(ds.dsn)}_{step_id}"
                    ds_label = f'{ds_id}[("<b>{dd.name}</b><br/>{ds.dsn}")]'
                
                disp_upper = ds.disp.upper()
                
                # Check if it's an output (, implies its new)
                is_output = (
                    "NEW" in disp_upper 
                    or "MOD" in disp_upper 
                    or disp_upper.startswith("(,") 
                    or disp_upper == ""
                )


                edge_label_safe = ds.disp.replace('"', "'")
                if is_output:
                    # Step writes to Dataset
                    mermaid_lines.append(f'  {step_id} -->|"{edge_label_safe}"| {ds_label}')                
                else:
                    # Input dataset Dataset feeds into Step
                    mermaid_lines.append(f'  {ds_label} -->|"{edge_label_safe}"| {step_id}')
        
        mermaid_lines.append('  end')  

        if step_idx < len(job.steps) - 1:             
            next_step = job.steps[step_idx + 1]
            next_step_id = f"Step{step_idx+2}_{sanitize_id(next_step.name)}"
            step_sequence_edges.append(f"  {step_id} ==> {next_step_id}")
    # Append all dataset <-> step connection lines
    if step_sequence_edges:
        mermaid_lines.append("")
        mermaid_lines.extend(step_sequence_edges)
    print("\n".join(mermaid_lines))
    return "\n".join(mermaid_lines)
    


def process_diagram(lines: Sequence[str]) -> str:
    logical_statements = preprocess_lines(lines)
    jclJob = parse_statements(logical_statements)
    output_diagram = design_diagram(jclJob)
    with open('mermaid.mmd','w') as file:
        file.write(output_diagram)


if __name__ == "__main__":
    main()