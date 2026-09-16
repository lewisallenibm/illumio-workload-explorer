"""Build the plain-English guide displayed by the web Settings documentation viewer.

Run ``python -m pip install -r requirements-docs.txt`` once, then run this
script after editing the guide text. The web application serves only the page
images; this script keeps the source PDF with the project documentation.
"""

from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "app" / "web" / "static" / "docs"
# The viewer presents rendered pages, so the source PDF remains project
# documentation instead of being exposed through a browser download URL.
PDF_PATH = ROOT / "docs" / "Illumio_CMDB_Working_Guide.pdf"


def build_pdf():
    DOCS.mkdir(parents=True, exist_ok=True)
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("GuideTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#111827"), spaceAfter=14)
    subtitle = ParagraphStyle("GuideSubtitle", parent=styles["BodyText"], fontSize=12, leading=17, textColor=colors.HexColor("#4b5563"), spaceAfter=18)
    heading = ParagraphStyle("GuideHeading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=10)
    body = ParagraphStyle("GuideBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.8, leading=15.4, textColor=colors.HexColor("#20242b"), spaceAfter=9, alignment=TA_LEFT)
    bullet = ParagraphStyle("GuideBullet", parent=body, leftIndent=16, firstLineIndent=-10, bulletIndent=4, spaceAfter=7)
    small = ParagraphStyle("GuideSmall", parent=body, fontSize=9.5, leading=13.2, textColor=colors.HexColor("#5b6472"), spaceAfter=8)

    def page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        canvas.drawString(0.72 * inch, 0.5 * inch, "Illumio and CMDB working guide")
        canvas.drawRightString(7.78 * inch, 0.5 * inch, f"Page {doc.page}")
        canvas.restoreState()

    story = [
        Paragraph("Illumio and CMDB Working Guide", title),
        Paragraph("A quick, plain-English look at what the tool does, what it checks, and what still needs real-world testing.", subtitle),
        Paragraph("What this tool is for", heading),
        Paragraph("The goal is simple: put the Illumio view of a system next to the CMDB view, find differences, and keep a record of what was reviewed. It is a working guide, not a final operating procedure. We will update it as the team confirms the real process and source data.", body),
        Paragraph("The basic flow", heading),
        Paragraph("1. Load the Illumio workload view. This can come from a mock dataset, a Workloader CSV export, or eventually a real PCE read-only API sync.", bullet),
        Paragraph("2. Load the CMDB or inventory file. The tool previews it first, then keeps the currently usable snapshot if the new file has a problem.", bullet),
        Paragraph("3. Run reconciliation. The tool compares the saved snapshots and shows the differences worth reviewing.", bullet),
        Paragraph("4. Review, approve, skip, or investigate the results. Approval is local to the tool; it does not change Illumio by itself.", bullet),
        Spacer(1, 0.08 * inch),
        Paragraph("Why the screens stay fast", heading),
        Paragraph("The data is saved in PostgreSQL. Searching, filtering, sorting, and page changes ask the database only for the small page you are viewing, instead of reopening an export file or loading every result into the browser.", body),
        PageBreak(),
        Paragraph("Where the workload information comes from", heading),
        Paragraph("The application treats a mock generator, Workloader export, and real Illumio API as sources, not separate versions of the product. Once data is accepted, it goes through the same cleanup and storage path.", body),
        Paragraph("PCE API sync", heading),
        Paragraph("When real PCE mode is configured, the application asks for workloads through HTTPS. It requests up to 500 records at a time, moves to the next offset, and repeats until the PCE indicates the final page. For roughly 40,000 workloads, that is about 80 normal API requests behind one sync action.", body),
        Paragraph("Workloader CSV", heading),
        Paragraph("A Workloader export does not contact the PCE. The tool looks for a usable identity, preferably an Illumio href and otherwise a safe hostname match. It recognizes common column aliases, keeps useful unmapped source fields for traceability, and surfaces duplicates instead of quietly merging them.", body),
        Paragraph("CMDB or inventory file", heading),
        Paragraph("The CMDB import maps real-world column names into the expected Application, Role, Environment, and Location values. A new file is staged and checked before it replaces the active CMDB snapshot. If it fails partway through, the previous usable snapshot remains available.", body),
        Paragraph("What normalizing means", heading),
        Paragraph("Different sources may call the same idea hostname, MachineName, app, application, env, or something else. Normalizing converts those variations into one shared format so ordinary app screens can work the same way regardless of the original source.", body),
        PageBreak(),
        Paragraph("What reconciliation checks", heading),
        Paragraph("The tool matches CMDB records to Illumio workloads using a normalized hostname. Exact normalized matches come first. A short hostname and FQDN are treated as a possible match only when there is one unambiguous candidate.", body),
        Paragraph("For each safe match, it compares the CMDB expectation to the labels currently saved for the Illumio workload:", body),
        Paragraph("• Application\n• Role\n• Environment\n• Location", bullet),
        Paragraph("Common result types", heading),
        Paragraph("LABEL_MISMATCH means both sides have a value but they do not agree. LABEL_MISSING means CMDB expects a label that the Illumio snapshot does not contain. NO_EXPECTED_VALUE means the CMDB did not provide the expectation. MISSING_IN_ILLUMIO means no safe workload match was found; it does not by itself mean a VEN is absent, unhealthy, or offline.", body),
        Paragraph("Duplicates and uncertainty", heading),
        Paragraph("When multiple records could match, the application reports an ambiguous result rather than guessing. The same is true when a record exists in Illumio but not in the chosen CMDB snapshot, or vice versa. Those are items for a person to investigate.", body),
        Paragraph("What is saved", heading),
        Paragraph("The database keeps the active snapshots, their import/sync history, reconciliation runs, and actionable results. This lets the team filter and review a particular run without rereading a source file.", body),
        PageBreak(),
        Paragraph("Approvals, PCE safety, and next testing", heading),
        Paragraph("Approve Selected changes a reconciliation result from pending to approved inside this application. It does not contact Illumio and it does not change a live label.", body),
        Paragraph("Apply Approved is different", heading),
        Paragraph("The code path for a real PCE write-back exists but stays guarded. It requires both real-PCE mode and a separate write-back setting. Before any write, the application re-reads the workload and rejects a request if the PCE label has changed since the reconciliation snapshot.", body),
        Paragraph("What still needs confirmation", heading),
        Paragraph("Before real write-back is used, the team needs approved non-production testing, confirmed label-key conventions, and an authorized sample change. For example, the real environment may use app or application as the label key. The tool should not assume that detail.", body),
        Paragraph("Good next tests", heading),
        Paragraph("Use the Settings PCE Connection Test with approved read-only credentials.", bullet, bulletText="•"),
        Paragraph("Import representative Workloader and CMDB files, including incomplete and duplicate examples.", bullet, bulletText="•"),
        Paragraph("Review reconciliation results with the people who own the source data.", bullet, bulletText="•"),
        Paragraph("Test scheduled artifacts in the safe local outbox before enabling any Email or Box delivery.", bullet, bulletText="•"),
        Paragraph("Add sign-in, access controls, durable job processing, and deployment safeguards before public access.", bullet, bulletText="•"),
        Paragraph("This guide is intentionally short. The application and operating process may change as the pilot turns into an agreed production workflow.", small),
    ]
    SimpleDocTemplate(str(PDF_PATH), pagesize=letter, rightMargin=0.72 * inch, leftMargin=0.72 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch).build(story, onFirstPage=page_number, onLaterPages=page_number)


def render_pages():
    document = fitz.open(PDF_PATH)
    for old in DOCS.glob("illumio-cmdb-guide-page-*.png"):
        old.unlink()
    for number, page in enumerate(document, 1):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.65, 1.65), alpha=False)
        pix.save(DOCS / f"illumio-cmdb-guide-page-{number}.png")


if __name__ == "__main__":
    build_pdf()
    render_pages()
