"""system_control/security - Windows OS security surface control: Defender
(real-time protection/scans/exclusions), Security Center's view of all
registered antivirus products, ransomware-specific Controlled Folder
Access, BitLocker volume encryption, local user accounts, and local
password/lockout policy (PowerShell/manage-bde/net-backed). Distinct
from the top-level security/ package, which is ULTRON's OWN internal
auth/encryption/voice-lock/face-lock/privacy layer, not the Windows
OS's security features - these classes control the operating system's
security posture, not Ultron itself.
"""
