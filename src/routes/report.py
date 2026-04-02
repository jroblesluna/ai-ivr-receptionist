from flask import Blueprint, render_template, abort
import reports

report_bp = Blueprint("report", __name__)


@report_bp.route("/report/<report_id>")
def view_report(report_id):
    data = reports.load(report_id)
    if not data:
        abort(404)
    return render_template("report.html", r=data)
