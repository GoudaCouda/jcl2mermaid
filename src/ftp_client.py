import argparse
import os
import sys
from typing import Sequence
import getpass
from ftplib import FTP
from jcl2mermaid import process_diagram
from dotenv import load_dotenv
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

def parse_args() -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="jcl2mermaid",
        description="a CLI tool that will download your jcl program and create a mermaid diagram from it to visualize the flow of execution",
    )

    parser.add_argument("--downloadmethod", help="Desired method to obtain the jcl. Ex. ftp, ssh, zowe, or local", default=os.getenv("DOWNLOAD_METHOD", "ftp"), choices=["ftp", "ssh", "zowe", "local"])
    parser.add_argument("--jclname", help="Full Name of the jcl you will download. Ex. HLQ.LIB.SRC(JCLSRC)", required=True)
    parser.add_argument("--username", help="Username for your desired Download Method", default=os.getenv("DOWNLOAD_USERNAME"))
    parser.add_argument("--hostname", help="Host Name for Download", default=os.getenv("DOWNLOAD_HOSTNAME"))
    parser.add_argument("--designtype", "--format", "-t", dest="designtype", help="Diagram design type / format (mermaid, d2, graphviz)", default=os.getenv("DESIGN_TYPE", "mermaid"), choices=["mermaid", "d2", "graphviz", "dot", "mmd"])
    parser.add_argument("-o", "--output", help="Output path for the generated diagram", default=None) 
    parser.add_argument("-p", "--print", help="Print the diagram to the console", action="store_true") 
    parser.add_argument("-c","--include-comments",help="If you wish to include comments in the graph output",action="store_true")

    return parser.parse_args()

def download_via_ftp():
    pass

def run_app(args: argparse.Namespace):
    lines = []
    if args.downloadmethod == "ftp":
        if not args.hostname:
            logging.error("Error: Hostname is required for FTP download.")
            return 1
        password = os.getenv("DOWNLOAD_PASSWORD") or getpass.getpass("Enter Password: ")
        logging.info(f"Connecting to FTP server at {args.hostname}...")
        with FTP(args.hostname) as ftp:
            ftp.login(args.username, password)
            logging.info(f"Downloading JCL dataset: {args.jclname}...")
            ftp.retrlines(f"RETR '{args.jclname}'", lines.append)
        logging.info("Download complete.")

    elif args.downloadmethod == "ssh":
        password = os.getenv("DOWNLOAD_PASSWORD") or getpass.getpass("Enter Password: ")
    elif args.downloadmethod == "zowe":
        # check for zowe config
        return 0
    elif args.downloadmethod == "local":
        logging.info(f"Reading local JCL file: {args.jclname}...")
        with open(args.jclname, "r", encoding="utf-8") as f:
            for line in f:
                lines.append(line.rstrip('\n'))

    logging.info("Parsing JCL statements...")
    output_diagram = process_diagram(lines, args)

    if args.print:
        print(output_diagram)
    else:
        designtype = getattr(args, "designtype", "mermaid").lower()
        ext_map = {"d2": "d2", "graphviz": "dot", "dot": "dot", "mermaid": "mmd", "mmd": "mmd"}
        ext = ext_map.get(designtype, "mmd")
        if args.output:
            output_path = Path(args.output)
            if not output_path.suffix:
                output_path = output_path.with_suffix(f".{ext}")
        else:
            clean_name = Path(args.jclname).stem.replace("(", "").replace(")", "")
            output_path = Path.cwd() / f"{clean_name}.{ext}"
        output_path.write_text(output_diagram, encoding="utf-8")
        logging.info(f"Successfully generated diagram: {output_path}")
        
    return 0

    


def main():
    args = parse_args()

    if args.print:
        logging.getLogger().setLevel(logging.WARNING)

    status = run_app(args)
    sys.exit(status)


if __name__ == "__main__":
    main()