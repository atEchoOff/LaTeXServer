import os
import subprocess
import tempfile
import zipfile
from flask import Flask, request, send_file, abort, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app) # allow requests from files (plainTeXt is a file)

# Save uploads while uploading chunks
UPLOAD_FOLDER = 'uploads'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/compile', methods=['POST'])
def handle_compilation():
    action = request.args.get('action')
    upload_id = request.args.get('upload_id')

    if not action or not upload_id or not str(upload_id).replace('-', '').isalnum() or not str(upload_id).startswith("plaintext"):
        abort(400, "Invalid parameters") # intentionally vague, security by obscurity!
        
    final_zip_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{upload_id}.zip")

    if action == 'upload':
        # User is trying to upload a chunk of a zip
        chunk = request.data
        if not chunk:
            abort(400, "Missing data on upload")
        try:
            # Write chunk to file
            with open(final_zip_path, 'ab') as f:
                f.write(chunk)
            return make_response({"status": "chunk received"}, 200)
        except IOError as e:
            abort(500, f"Server error while writing file chunk: {e}")

    elif action == 'compile':
        # User is trying to compile their finished zip
        if not os.path.exists(final_zip_path):
            abort(400, "Chunks must be uploaded before compiling")
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(final_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                main_tex_path = os.path.join(temp_dir, 'main.tex')
                if not os.path.exists(main_tex_path):
                    abort(400, "main.tex was not uploaded")

                # Compile a few times to get bibtex working
                commands = [
                    ['pdflatex', '-interaction=nonstopmode', '-no-shell-escape', 'main.tex'],
                    ['bibtex', 'main'],
                    ['pdflatex', '-interaction=nonstopmode', '-no-shell-escape', 'main.tex'],
                    ['pdflatex', '-interaction=nonstopmode', '-no-shell-escape', 'main.tex']
                ]

                for cmd in commands:
                    subprocess.run(
                        cmd,
                        cwd=temp_dir,
                        check=False,
                        timeout=30, # stop after 30s
                        capture_output=True
                    )
                
                output_pdf_path = os.path.join(temp_dir, 'main.pdf')
                if not os.path.exists(output_pdf_path):
                    log_path = os.path.join(temp_dir, 'main.log')
                    if os.path.exists(log_path):
                        with open(log_path, 'r', errors='ignore') as log_file:
                            log_content = "".join(log_file.readlines())
                        abort(400, f"PDF compilation failed. Log: \n{log_content}")
                    else:
                        abort(500, "PDF compilation failed and no log file was generated.")

                return send_file(
                    output_pdf_path,
                    mimetype='application/pdf',
                    as_attachment=True,
                    download_name='output.pdf'
                )

            except subprocess.TimeoutExpired:
                abort(400, "Compilation timed out. Your LaTeX job took too long to run.")
            except Exception as e:
                abort(500, f"An unexpected error occurred: {e}")
            finally:
                # Clean up!
                if os.path.exists(final_zip_path):
                    os.remove(final_zip_path)
    else:
        abort(400, "An unknown error occurred.")

if __name__ == '__main__':
    app.run(debug=True, port=8172)