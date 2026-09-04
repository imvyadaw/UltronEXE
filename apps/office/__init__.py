"""Office automations: Word, Excel, PowerPoint, Outlook, OneNote, Teams, Access."""

from apps.office.word import WordApp
from apps.office.excel import ExcelApp
from apps.office.powerpoint import PowerPointApp
from apps.office.outlook import OutlookApp
from apps.office.onenote import OneNoteApp
from apps.office.teams import TeamsApp
from apps.office.access import AccessApp

__all__ = ["WordApp", "ExcelApp", "PowerPointApp", "OutlookApp", "OneNoteApp", "TeamsApp", "AccessApp"]
