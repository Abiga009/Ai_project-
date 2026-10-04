"""SITCO: solicitud y seguimiento local de transporte de compras."""

from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


HOST = os.environ.get("SITCO_HOST", "127.0.0.1")
PORT = int(os.environ.get("SITCO_PORT", "8000"))
DATABASE = Path(os.environ.get("SITCO_DATABASE", Path(__file__).with_name("sitco.db")))
MAX_BODY_BYTES = 16_384
STATUSES = {"solicitado", "confirmado", "en preparación", "en camino", "entregado"}

PAGE = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#146b50">
  <title>SITCO | Transporte de compras</title>
  <style>
    :root {
      color-scheme: light;
      --green: #146b50;
      --green-dark: #0d4e3a;
      --mint: #e8f4ee;
      --ink: #1c3028;
      --muted: #65776f;
      --line: #dce6e0;
      --paper: #fff;
      --bg: #f4f7f5;
      --danger: #a52c2c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    header {
      background: var(--green);
      color: white;
      padding: 18px max(24px, calc((100% - 1100px) / 2));
    }
    .brand { font-size: 1.15rem; font-weight: 800; letter-spacing: .04em; }
    .brand span { display: block; font-size: .78rem; font-weight: 400; opacity: .85; }
    main { max-width: 1100px; margin: 38px auto; padding: 0 22px 40px; }
    .intro { margin-bottom: 24px; }
    h1 { margin: 0 0 6px; font-size: clamp(1.7rem, 4vw, 2.3rem); line-height: 1.2; }
    h2 { margin: 0 0 18px; font-size: 1.2rem; }
    p { margin: 0; color: var(--muted); }
    .layout { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(280px, .8fr); gap: 22px; }
    .card { background: var(--paper); border: 1px solid var(--line); border-radius: 14px; padding: 24px; box-shadow: 0 5px 20px #153b2810; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
    .field { display: flex; flex-direction: column; gap: 6px; }
    .wide { grid-column: 1 / -1; }
    label { font-size: .9rem; font-weight: 650; }
    input, textarea, select {
      width: 100%; border: 1px solid #cbd8d0; border-radius: 8px;
      background: white; color: var(--ink); font: inherit; padding: 10px 11px;
    }
    input:focus, textarea:focus, select:focus { outline: 3px solid #146b5030; border-color: var(--green); }
    textarea { min-height: 82px; resize: vertical; }
    .hint { font-size: .8rem; color: var(--muted); }
    button {
      border: 0; border-radius: 8px; background: var(--green); color: white;
      font: inherit; font-weight: 700; padding: 11px 16px; cursor: pointer;
    }
    button:hover { background: var(--green-dark); }
    button:disabled { opacity: .65; cursor: wait; }
    .submit { margin-top: 18px; width: 100%; }
    .result { margin-top: 14px; border-radius: 8px; padding: 12px; background: var(--mint); }
    .result:empty { display: none; }
    .result.error { background: #fff0f0; color: var(--danger); }
    .tracking { margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--line); }
    .tracking-form { display: grid; grid-template-columns: 1fr 1fr auto; align-items: end; gap: 10px; }
    .status { display: inline-block; border-radius: 999px; background: var(--mint); color: var(--green-dark); padding: 4px 10px; font-weight: 700; font-size: .86rem; text-transform: capitalize; }
    .details { margin-top: 13px; }
    .details p { margin: 5px 0; }
    .details strong { color: var(--ink); }
    footer { max-width: 1100px; padding: 0 22px 28px; margin: auto; color: var(--muted); font-size: .82rem; }
    @media (max-width: 760px) {
      main { margin-top: 25px; }
      .layout { grid-template-columns: 1fr; }
      .tracking-form { grid-template-columns: 1fr; }
      .tracking-form button { width: 100%; }
    }
    @media (max-width: 480px) {
      .card { padding: 18px; }
      .grid { grid-template-columns: 1fr; }
      .wide { grid-column: auto; }
    }
  </style>
</head>
<body>
  <header><div class="brand">SITCO<span>Sistema de Transporte de Compras del Supermercado</span></div></header>
  <main>
    <section class="intro">
      <h1>Tu compra, hasta tu casa</h1>
      <p>Solicita el transporte de tus compras grandes y consulta el estado de tu entrega.</p>
    </section>
    <div class="layout">
      <section class="card">
        <h2>Solicitar transporte</h2>
        <form id="request-form">
          <div class="grid">
            <div class="field">
              <label for="customer_name">Nombre completo</label>
              <input id="customer_name" name="customer_name" maxlength="100" autocomplete="name" required>
            </div>
            <div class="field">
              <label for="phone">Teléfono de contacto</label>
              <input id="phone" name="phone" maxlength="30" autocomplete="tel" required>
            </div>
            <div class="field wide">
              <label for="address">Dirección de entrega</label>
              <input id="address" name="address" maxlength="250" autocomplete="street-address" required>
            </div>
            <div class="field">
              <label for="zone">Comuna o zona</label>
              <input id="zone" name="zone" maxlength="100" required>
            </div>
            <div class="field">
              <label for="delivery_date">Fecha preferida</label>
              <input id="delivery_date" name="delivery_date" type="date" required>
            </div>
            <div class="field">
              <label for="delivery_time">Horario preferido</label>
              <select id="delivery_time" name="delivery_time" required>
                <option value="">Selecciona un horario</option>
                <option>09:00 - 12:00</option>
                <option>12:00 - 15:00</option>
                <option>15:00 - 18:00</option>
                <option>18:00 - 21:00</option>
              </select>
            </div>
            <div class="field">
              <label for="purchase_size">Tamaño aproximado de la compra</label>
              <select id="purchase_size" name="purchase_size" required>
                <option value="">Selecciona una opción</option>
                <option>Grande</option>
                <option>Muy grande</option>
                <option>Voluminosa o pesada</option>
              </select>
            </div>
            <div class="field wide">
              <label for="notes">Productos o indicaciones para la entrega</label>
              <textarea id="notes" name="notes" maxlength="1000" placeholder="Por ejemplo: cajas, productos frágiles, referencias para llegar"></textarea>
            </div>
          </div>
          <p class="hint">El supermercado confirmará la disponibilidad y el costo del servicio.</p>
          <button class="submit" id="submit-button" type="submit">Enviar solicitud</button>
        </form>
        <div id="form-result" class="result" role="status" aria-live="polite"></div>
      </section>
      <aside class="card">
        <h2>Consultar mi solicitud</h2>
        <p>Ingresa el código recibido y el teléfono usado al solicitar el servicio.</p>
        <form id="tracking-form" class="tracking">
          <div class="tracking-form">
            <div class="field">
              <label for="tracking_id">Código de solicitud</label>
              <input id="tracking_id" name="tracking_id" maxlength="8" placeholder="Ej.: A1B2C3D4" required>
            </div>
            <div class="field">
              <label for="tracking_phone">Teléfono</label>
              <input id="tracking_phone" name="tracking_phone" maxlength="30" autocomplete="tel" required>
            </div>
            <button type="submit">Consultar</button>
          </div>
        </form>
        <div id="tracking-result" class="result" role="status" aria-live="polite"></div>
      </aside>
    </div>
  </main>
  <footer>SITCO · La solicitud queda pendiente hasta que el supermercado confirme el servicio.</footer>
  <script>
    const formResult = document.querySelector("#form-result");
    const trackingResult = document.querySelector("#tracking-result");

    function showMessage(element, message, isError = false) {
      element.textContent = message;
      element.classList.toggle("error", isError);
    }

    document.querySelector("#request-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const button = document.querySelector("#submit-button");
      const data = Object.fromEntries(new FormData(form).entries());
      button.disabled = true;
      showMessage(formResult, "Enviando solicitud...");
      try {
        const response = await fetch("/api/requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "No se pudo enviar la solicitud.");
        document.querySelector("#tracking_id").value = result.id;
        document.querySelector("#tracking_phone").value = data.phone;
        showMessage(formResult, `Solicitud registrada. Tu código es ${result.id}. Guárdalo para consultar el estado.`);
        form.reset();
      } catch (error) {
        showMessage(formResult, error.message, true);
      } finally {
        button.disabled = false;
      }
    });

    document.querySelector("#tracking-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = document.querySelector("#tracking_id").value.trim().toUpperCase();
      const phone = document.querySelector("#tracking_phone").value.trim();
      showMessage(trackingResult, "Buscando solicitud...");
      try {
        const response = await fetch(`/api/requests/${encodeURIComponent(id)}?phone=${encodeURIComponent(phone)}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "No se pudo consultar la solicitud.");
        trackingResult.classList.remove("error");
        trackingResult.replaceChildren();
        const status = document.createElement("span");
        status.className = "status";
        status.textContent = result.status;
        const details = document.createElement("div");
        details.className = "details";
        const destination = document.createElement("p");
        destination.textContent = `Destino: ${result.zone}`;
        const schedule = document.createElement("p");
        schedule.textContent = `Fecha y horario solicitados: ${result.delivery_date}, ${result.delivery_time}`;
        const note = document.createElement("p");
        note.textContent = result.status === "solicitado"
          ? "El supermercado aún debe confirmar la disponibilidad y el costo."
          : "El supermercado actualizará el estado de tu entrega.";
        details.append(destination, schedule, note);
        trackingResult.append(status, details);
      } catch (error) {
        showMessage(trackingResult, error.message, true);
      }
    });
  </script>
</body>
</html>
"""


def initialize_database() -> None:
    """Create the requests table on first launch."""
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS transport_requests (
                id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                zone TEXT NOT NULL,
                delivery_date TEXT NOT NULL,
                delivery_time TEXT NOT NULL,
                purchase_size TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'solicitado',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def validate_request(data: object) -> tuple[dict[str, str] | None, str | None]:
    if not isinstance(data, dict):
        return None, "El contenido de la solicitud debe ser un objeto JSON."

    fields = {
        "customer_name": 100,
        "phone": 30,
        "address": 250,
        "zone": 100,
        "delivery_date": 10,
        "delivery_time": 20,
        "purchase_size": 40,
        "notes": 1000,
    }
    cleaned: dict[str, str] = {}
    for field, max_length in fields.items():
        value = data.get(field, "")
        if not isinstance(value, str):
            return None, f"El campo {field} debe ser texto."
        value = value.strip()
        if len(value) > max_length:
            return None, f"El campo {field} supera el máximo de {max_length} caracteres."
        if field != "notes" and not value:
            return None, f"El campo {field} es obligatorio."
        cleaned[field] = value

    try:
        date.fromisoformat(cleaned["delivery_date"])
    except ValueError:
        return None, "La fecha de entrega no es válida."

    if not re.fullmatch(r"[0-9+()\-\s]{7,30}", cleaned["phone"]):
        return None, "Ingresa un teléfono de contacto válido."
    if cleaned["delivery_time"] not in {
        "09:00 - 12:00",
        "12:00 - 15:00",
        "15:00 - 18:00",
        "18:00 - 21:00",
    }:
        return None, "Selecciona un horario disponible."
    if cleaned["purchase_size"] not in {"Grande", "Muy grande", "Voluminosa o pesada"}:
        return None, "Selecciona el tamaño aproximado de la compra."
    return cleaned, None


class SitcoHandler(BaseHTTPRequestHandler):
    server_version = "SITCO/1.0"

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)
            return

        match = re.fullmatch(r"/api/requests/([A-Fa-f0-9]{8})", parsed.path)
        if match:
            phone = parse_qs(parsed.query).get("phone", [""])[0].strip()
            if not phone:
                self.send_json(400, {"error": "Ingresa el teléfono asociado a la solicitud."})
                return
            with sqlite3.connect(DATABASE) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """
                    SELECT id, phone, zone, delivery_date, delivery_time, status
                    FROM transport_requests
                    WHERE id = ? AND phone = ?
                    """,
                    (match.group(1).upper(), phone),
                ).fetchone()
            if row is None:
                self.send_json(404, {"error": "No encontramos una solicitud con ese código y teléfono."})
                return
            self.send_json(200, dict(row))
            return

        self.send_json(404, {"error": "Recurso no encontrado."})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/requests":
            self.send_json(404, {"error": "Recurso no encontrado."})
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self.send_json(415, {"error": "El contenido debe enviarse como application/json."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Tamaño de solicitud inválido."})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self.send_json(413, {"error": "La solicitud está vacía o excede el tamaño permitido."})
            return
        try:
            data = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "El cuerpo de la solicitud no contiene JSON válido."})
            return

        cleaned, error = validate_request(data)
        if error:
            self.send_json(400, {"error": error})
            return
        if cleaned is None:
            self.send_json(400, {"error": "No se pudo validar la solicitud."})
            return

        request_id = secrets.token_hex(4).upper()
        with sqlite3.connect(DATABASE) as connection:
            connection.execute(
                """
                INSERT INTO transport_requests (
                    id, customer_name, phone, address, zone, delivery_date,
                    delivery_time, purchase_size, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    cleaned["customer_name"],
                    cleaned["phone"],
                    cleaned["address"],
                    cleaned["zone"],
                    cleaned["delivery_date"],
                    cleaned["delivery_time"],
                    cleaned["purchase_size"],
                    cleaned["notes"],
                ),
            )
        self.send_json(201, {"id": request_id, "status": "solicitado"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), SitcoHandler)
    print(f"SITCO está disponible en http://{HOST}:{PORT}")
    print(f"Base de datos: {DATABASE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando SITCO...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
