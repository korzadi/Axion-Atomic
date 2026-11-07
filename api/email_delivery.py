"""Entrega de correo transaccional por SMTP con TLS obligatorio."""
from email.message import EmailMessage
import smtplib
import ssl


def email_delivery_configured(settings) -> bool:
    username = bool(settings.smtp_username)
    password = bool(settings.smtp_password)
    return bool(
        settings.smtp_host
        and settings.email_from
        and (settings.smtp_starttls or settings.smtp_ssl)
        and not (settings.smtp_starttls and settings.smtp_ssl)
        and username == password
        and 1 <= settings.smtp_port <= 65535
    )


def send_transactional_email(*, settings, recipient: str, subject: str, body: str) -> None:
    if not email_delivery_configured(settings):
        raise RuntimeError("El correo transaccional no está configurado")
    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    context = ssl.create_default_context()
    if settings.smtp_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15, context=context) as server:
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password or "")
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password or "")
            server.send_message(message)


def send_verification_email(*, settings, recipient: str, token: str) -> None:
    link = settings.oauth_public_base_url.rstrip("/") + "/#verify-email=" + token
    send_transactional_email(
        settings=settings,
        recipient=recipient,
        subject="Verifica tu correo · AXION ATOMIC",
        body=(
            "Para verificar tu correo y activar tu cuenta AXION ATOMIC, abre este enlace:\n\n"
            + link
            + "\n\nEl enlace caduca en 30 minutos y solo puede utilizarse una vez. "
            "Si no solicitaste esta cuenta, ignora este mensaje."
        ),
    )


def send_password_reset_email(*, settings, recipient: str, token: str) -> None:
    link = settings.oauth_public_base_url.rstrip("/") + "/#reset-password=" + token
    send_transactional_email(
        settings=settings,
        recipient=recipient,
        subject="Recuperación de contraseña · AXION ATOMIC",
        body=(
            "Para elegir una nueva contraseña de AXION ATOMIC, abre este enlace:\n\n"
            + link
            + "\n\nEl enlace caduca en 30 minutos y solo puede utilizarse una vez. "
            "Si no solicitaste este cambio, ignora este mensaje."
        ),
    )
