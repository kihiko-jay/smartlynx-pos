from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email import encoders

from app.core.config import settings

logger = logging.getLogger("dukapos.email")


def send_password_reset_email(*, to_email: str, recipient_name: str, reset_token: str) -> None:
    if not settings.mail_enabled:
        raise RuntimeError("SMTP is not configured")

    reset_base = settings.PASSWORD_RESET_URL or f"{settings.FRONTEND_URL.rstrip('/')}/reset-password"
    reset_link = f"{reset_base}?token={reset_token}&email={to_email}"

    msg = EmailMessage()
    msg["Subject"] = "Reset your Smartlynx password"
    msg["From"] = settings.MAIL_FROM
    msg["To"] = to_email
    msg.set_content(
        f"Hello {recipient_name},\n\n"
        f"Use the link below to reset your password. This link expires in 1 hour.\n\n"
        f"{reset_link}\n\n"
        f"If you did not request this, you can ignore this email.\n"
    )

    try:
        if settings.SMTP_USE_SSL:
            smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        else:
            smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        with smtp as server:
            server.ehlo()
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                server.starttls()
                server.ehlo()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
        raise


def send_purchase_order_email(
    *,
    to_email: str,
    recipient_name: str,
    po_number: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    supplier_name: str,
    message: str = "",
) -> None:
    """
    Send a Purchase Order as PDF attachment via email.
    
    Args:
        to_email: Recipient's email address
        recipient_name: Recipient's name (for greeting)
        po_number: PO number (for subject line)
        pdf_bytes: PDF document as bytes
        pdf_filename: Filename for the attachment (e.g., "PO-2024-001.pdf")
        supplier_name: Supplier name (for reference)
        message: Optional custom message body
    
    Raises:
        RuntimeError: If SMTP is not configured
        smtplib.SMTPException: If email delivery fails
    """
    if not settings.mail_enabled:
        raise RuntimeError("SMTP is not configured")
    
    # Build email message
    msg = EmailMessage()
    msg["Subject"] = f"Purchase Order {po_number} from {settings.STORE_NAME}"
    msg["From"] = settings.MAIL_FROM
    msg["To"] = to_email
    
    # Email body
    body = f"""Hello {recipient_name},

Please find attached the Purchase Order {po_number} for your review.

{message or "Please contact us if you have any questions."}

Best regards,
{settings.STORE_NAME}
"""
    
    msg.set_content(body)
    
    # Attach PDF
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
    )
    
    try:
        if settings.SMTP_USE_SSL:
            smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        else:
            smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        
        with smtp as server:
            server.ehlo()
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                server.starttls()
                server.ehlo()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info("PO email sent to %s (PO %s)", to_email, po_number)
    except Exception:
        logger.exception("Failed to send PO email to %s (PO %s)", to_email, po_number)
        raise
