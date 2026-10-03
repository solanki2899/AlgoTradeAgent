import logging
from logging.handlers import RotatingFileHandler
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import sys
from datetime import datetime

# Setup 50MB Rotating Logger with UTF-8 encoding (fixes ₹ symbol crash on Windows)
def setup_logger():
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    log_file = os.path.join(log_dir, f"algo_session_{datetime.now().strftime('%Y%m%d')}.log")
    
    logger = logging.getLogger("AlgoAgent")
    logger.setLevel(logging.INFO)
    
    # 50MB max size, keep 5 backups — with UTF-8 encoding to support ₹ and other Unicode chars
    file_handler = RotatingFileHandler(
        log_file, maxBytes=50*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    # Also add a console handler with UTF-8 for live terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    return logger, log_file

logger, current_log_file = setup_logger()

def send_email_report(summary_text, log_file_path, email_user, email_pass, to_email):
    """Sends the 3:30 PM automated End of Day report."""
    try:
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = to_email
        msg['Subject'] = f"Algo Agent EOD Report - {datetime.now().strftime('%Y-%m-%d')}"

        msg.attach(MIMEText(summary_text, 'plain'))

        # Attach log file
        if os.path.exists(log_file_path):
            with open(log_file_path, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f"attachment; filename= {os.path.basename(log_file_path)}")
            msg.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_pass)
        text = msg.as_string()
        server.sendmail(email_user, to_email, text)
        server.quit()
        logger.info("EOD Email report sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email report: {e}")