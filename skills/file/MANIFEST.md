# File skills

| Tool | Module |
|---|---|
| list_directory, search_files, find_folder, read_file, get_file_info, create_folder, create_file, write_file, copy_file, move_file, delete_file, delete_folder, open_file | files/manager/manager.py |
| save_note, read_notes | memory/short_term/notes.py |
| extract_pdf_text, get_pdf_page_count, merge_pdfs, create_pdf_from_text | files/pdf/pdf.py |
| read_docx, create_docx, read_xlsx, create_xlsx | files/office/office.py |
| compress_files, extract_archive | files/compression/compression.py |
| (indexed file search - module only, not an AI tool by default) | files/search/indexed_search.py |

All five file modules are implemented. `files/pdf/` also has split_pdf/rotate_pdf
and `files/office/` also has read_pptx/create_pptx - real and callable directly,
just not in the default AI tool schema (see windows/__init__.py's SystemTools
facade for the full method list).
