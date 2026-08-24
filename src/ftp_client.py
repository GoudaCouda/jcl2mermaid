import argparse
import os
import sys
from typing import Sequence
import getpass
from ftplib import FTP
from dotenv import load_dotenv

def parse_args(argv) -> argparse.Namespace:
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="jcl2mermaid",
        description="a CLI tool that will download your jcl program and create a mermaid diagram from it to visualize the flow of execution",
    )

    parser.add_argument("--downloadmethod",help="Desired method to obtain the jcl. Ex. ftp, ssh, zowe, or local",default=os.getenv("DOWNLOAD_METHOD","ftp"),choices=["ftp","ssh","zowe","local"])
    parser.add_argument("--jclname",help="Full Name of the jcl you will download. Ex. HLQ.LIB.SRC(JCLSRC)",required=True)
    parser.add_argument("--username",help="Username for your desired Download Method",default=os.getenv("DOWNLOAD_USERNAME"))
    parser.add_argument("--hostname",help="Host Name for Download",default=os.getenv("DOWNLOAD_HOSTNAME"))

    return parser.parse_args(argv)

def download_via_ftp():
    pass

def run_app(args: argparse.Namespace):

    if args.downloadmethod == "ftp":
        password = os.getenv("DOWNLOAD_PASSWORD") or getpass.getpass("Enter Password: ")
        lines = []
        with FTP(args.hostname) as ftp:
            ftp.login(args.username,password)
            ftp.retrlines(f"RETR '{args.jclname}'",lines.append)
        print("\n".join(lines))

    elif args.downloadmethod =="ssh":
        password = os.getenv("DOWNLOAD_PASSWORD") or getpass.getpass("Enter Password: ")
    elif args.downloadmethod =="zowe":
        # check for zowe config
        pass

    


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    status = run_app(args)
    return


if __name__ == "__main__":
    main()