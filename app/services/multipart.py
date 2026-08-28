"""Codificador multipart/form-data mínimo, sin dependencias.

Telegram y Chatwoot reciben archivos solo por multipart. El resto del proyecto
habla con ellos por urllib, así que se arma el cuerpo a mano en vez de sumar
`requests` solo para esto."""
import uuid


def encode(fields: dict[str, str], files: list[tuple[str, str, bytes, str]]) -> tuple[str, bytes]:
    """Arma el cuerpo. `files` son tuplas (campo, nombre_archivo, contenido, mime).
    Devuelve (content_type, cuerpo) listos para urllib."""
    boundary = f"----a3boundary{uuid.uuid4().hex}"
    sep = f"--{boundary}\r\n".encode()
    body = bytearray()
    for name, value in fields.items():
        if value is None:
            continue
        body += sep
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        body += f"{value}\r\n".encode("utf-8")
    for name, filename, content, mime in files:
        body += sep
        body += f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8")
        body += f"Content-Type: {mime}\r\n\r\n".encode("utf-8")
        body += content
        body += b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", bytes(body)
