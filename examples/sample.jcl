//JOB00100 JOB (ACCT101),'JCL TEST SUITE',CLASS=A,MSGCLASS=X,NOTIFY=&SYSUID
//* ===================================================================
//* STEP 1: CLEANUP / PRE-ALLOCATION DELETION (PGM: IEFBR14)
//* Tests: [DEL] tags, multi-line continuations, avoiding fake handoffs
//* ===================================================================
//STEP010  EXEC PGM=IEFBR14
//DEL01    DD DSN=APP.SAMPLE.SORTED.STAGE,
//            DISP=(MOD,DELETE,DELETE),
//            UNIT=SYSDA,SPACE=(TRK,(0))
//DEL02    DD DSN=APP.SAMPLE.DAILY.REPORT,
//            DISP=(MOD,DELETE),
//            UNIT=SYSDA,SPACE=(TRK,(0))
//*
//* ===================================================================
//* STEP 2: EXTRACT DATA & CREATE TEMPORARY PASSED FILE (PGM: IDCAMS)
//* ===================================================================
//STEP020  EXEC PGM=IDCAMS
//INFILE   DD DSN=PROD.CUSTOMER.MASTER(+1),DISP=SHR
//OUTPASS  DD DSN=&&TEMPRAW,
//            DISP=(NEW,PASS),
//            UNIT=SYSDA,
//            SPACE=(CYL,(10,5))
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  REPRO INFILE(INFILE) OUTFILE(OUTPASS)
/*
//*
//* ===================================================================
//* STEP 3: SORT THE PASSED DATA (PGM: SORT)
//* Tests: Consuming passed temp file, Scratch SORTWK, DISP=(,CATLG)
//* ===================================================================
//STEP030  EXEC PGM=SORT
//SORTIN   DD DSN=&&TEMPRAW,DISP=(OLD,DELETE)
//SORTOUT  DD DSN=APP.SAMPLE.SORTED.STAGE,
//            DISP=(,CATLG,DELETE),
//            UNIT=SYSDA,
//            SPACE=(CYL,(15,5))
//SORTWK01 DD UNIT=SYSDA,SPACE=(CYL,(5,5))
//SORTWK02 DD UNIT=SYSDA,SPACE=(CYL,(5,5)),DISP=(NEW,DELETE)
//SYSOUT   DD SYSOUT=*
//SYSIN    DD *
  SORT FIELDS=(1,10,CH,A,25,8,ZD,D)
/*
//*
//* ===================================================================
//* STEP 4: BUSINESS VALIDATION (PGM: VALD001)
//* Tests: STEPLIB, Read from prior step, GDG(+1) creation, NEW,CATLG
//* ===================================================================
//STEP040  EXEC PGM=NATBATCH,PARM="SYS=888"
//STEPLIB  DD DSN=APP.LOADLIB.PROD,DISP=SHR
//INPUTDD  DD DSN=APP.SAMPLE.SORTED.STAGE,DISP=SHR
//CONFIGDD DD DSN=PROD.PARMLIB(RULES01),DISP=SHR
//OUTRPT   DD DSN=APP.SAMPLE.DAILY.REPORT,
//            DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,
//            SPACE=(CYL,(5,2))
//OUTERR   DD DSN=APP.SAMPLE.ERROR.LOG(+1),
//            DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,
//            SPACE=(TRK,(5,2))
//SYSOUT   DD SYSOUT=*
//CMSYNIN DD *
LIBRAR,LIBRAR
%*
NATPROG
NATPROG
FIN
/*
//*
//* ===================================================================
//* STEP 5: AUDIT LOGGING (PGM: AUDIT01)
//* Tests: DISP=MOD (Append to persistent log)
//* ===================================================================
//STEP050  EXEC PGM=AUDIT01
//STEPLIB  DD DSN=APP.LOADLIB.PROD,DISP=SHR
//INPRPT   DD DSN=APP.SAMPLE.DAILY.REPORT,DISP=SHR
//AUDITLOG DD DSN=APP.GLOBAL.AUDIT.LOG,DISP=MOD
//SYSOUT   DD SYSOUT=*
//*
//* ===================================================================
//* STEP 6: ARCHIVE & BACKUP (PGM: IDCAMS)
//* Tests: DISP=(OLD,KEEP), GDG generation handoff
//* ===================================================================
//STEP060  EXEC PGM=IDCAMS
//INDD     DD DSN=APP.SAMPLE.DAILY.REPORT,DISP=(OLD,KEEP)
//OUTGDG   DD DSN=APP.BACKUP.REPORT.GDG(+1),
//            DISP=(NEW,CATLG,DELETE),
//            UNIT=SYSDA,
//            SPACE=(CYL,(5,2))
//SYSPRINT DD SYSOUT=*
//SYSIN    DD *
  REPRO INFILE(INDD) OUTFILE(OUTGDG)
/*
//