# Email skills

| Tool | Module |
|---|---|
| send_email, read_emails, search_emails, get_email_body, mark_as_read, delete_email | skills/email/gmail.py (`GmailClient`) |
| send_email, read_emails, search_emails, mark_as_read, delete_email | skills/email/outlook.py (`OutlookClient`) |
| list_templates, get_template, save_template, delete_template, render | skills/email/templates.py (`EmailTemplates`) |

Gmail uses Google OAuth (device/browser consent, token cached under
storage/cache/). Outlook uses MSAL device-code flow against Microsoft
Graph. All AI-callable (gmail_*, outlook_*, *_email_template tools -
see ai/new_skills_tools.py). Credentials are configured via .env - see
.env.example.
