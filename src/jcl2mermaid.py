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
    for i in logical_statements:
        print("\n" + i)
    return logical_statements

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


            current_step.name=JclStep(name=label, program=program_name)
            job.steps.append(current_step)

        elif operation == "DD":
            # Extract DSN and DISP 
            dsn_match = re.search(r"DSN=([^,\s]+)", params, re.IGNORECASE)
            disp_match = re.search(r"DISP=([^,\s]+|\([^)]+\))", params, re.IGNORECASE)

            dsn = dsn_match.group(1) if dsn_match else "TEMP.FILE"
            disp = disp_match.group(1) if disp_match else "SHR"

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
def generate_diagram(lines: Sequence[str],jclname) -> str:
    



    mermaid_lines = ["flowchart TD","\tsubgraph SGTitle [f{member_name}]"]
    # TODO: Core application logic
    pass


def main(argv: Sequence[str] | None = None) -> None:
    pass


if __name__ == "__main__":
    main()