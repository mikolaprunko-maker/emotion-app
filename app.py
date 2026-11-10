"""
AI-перекладач емоцій — веб-застосунок на Flask з інтеграцією Google Gemini API.
Автор: Прунько М.С., група АКП-25-3К, ІФНТУНГ
"""
import os
import time
from pathlib import Path
from typing import List

from flask import Flask, jsonify, render_template, request
from pydantic import BaseModel, Field, ValidationError

from google import genai
from google.genai import errors, types

BASE_DIR = Path(__file__).resolve().parent
MAX_LEN = 1000

# Емоції, які розпізнає застосунок, і їх емодзі
EMOTIONS = {
    "радість": "😊", "сум": "😢", "гнів": "😠", "страх": "😨", "тривога": "😰",
    "здивування": "😲", "любов": "❤️", "вдячність": "🙏", "втома": "😴", "нейтрально": "😐",
}

# Моделі Gemini з безкоштовним доступом. Якщо одна недоступна або вичерпано ліміт,
# застосунок автоматично пробує наступну.
DEFAULT_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"]

SYSTEM_PROMPT = f"""Ти – чуйний психолог-аналітик емоцій. Користувач надсилає текст українською
або іншою мовою. Визнач головну емоцію автора тексту строго з цього списку:
{", ".join(EMOTIONS)}.
Також вкажи до двох додаткових емоцій з того самого списку, якщо вони є.
Оціни впевненість від 0 до 100.
Поясни коротко (1–2 речення), які слова чи фрази вказують на цю емоцію.
Дай доречну практичну пораду (1–2 речення) з урахуванням емоції: підтримай, якщо людині погано,
порадій разом із нею, якщо їй добре.
Додай коротку надихаючу цитату відомої людини з автором, яка пасує до ситуації.
Відповідай українською мовою, доброзичливо. Не став медичних діагнозів."""


class EmotionResult(BaseModel):
    """Структура відповіді, яку ми вимагаємо від моделі (JSON Schema)."""
    emotion: str = Field(description="Головна емоція зі списку")
    secondary: List[str] = Field(default_factory=list, description="До двох додаткових емоцій зі списку")
    confidence: int = Field(ge=0, le=100, description="Впевненість, %")
    explanation: str = Field(description="Чому визначено саме цю емоцію")
    advice: str = Field(description="Порада користувачу")
    quote: str = Field(description="Надихаюча цитата з автором")


class AIServiceError(Exception):
    """Помилка, яку можна показати користувачу."""
    def __init__(self, message, status=503):
        super().__init__(message)
        self.message, self.status = message, status


def load_api_key():
    """Ключ береться зі змінної середовища GEMINI_API_KEY або з файлу api_key.txt."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    key_file = BASE_DIR / "api_key.txt"
    if not key and key_file.exists():
        key = key_file.read_text(encoding="utf-8-sig").strip()
    return key


API_KEY = load_api_key()
MODELS = [m for m in [os.environ.get("GEMINI_MODEL", "").strip()] if m] + DEFAULT_MODELS
client = genai.Client(api_key=API_KEY) if API_KEY else None
app = Flask(__name__)


def analyze_emotion(text: str) -> dict:
    """Надсилає текст у Gemini і повертає перевірений результат."""
    if client is None:
        raise AIServiceError("На сервері не налаштовано ключ Gemini API (GEMINI_API_KEY).", 500)

    last_error = None
    for model in MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"Текст користувача:\n\"\"\"{text}\"\"\"",
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_json_schema=EmotionResult.model_json_schema(),
                    temperature=0.4,
                ),
            )
            result = EmotionResult.model_validate_json(response.text or "")
            return normalize(result, model)
        except errors.ClientError as e:
            if e.code in (404, 429):          # модель недоступна або вичерпано ліміт – пробуємо наступну
                last_error = e
                continue
            if e.code in (400, 401, 403):
                raise AIServiceError("Ключ Gemini API недійсний або не має доступу. Перевірте ключ.", 500)
            raise AIServiceError(f"Помилка запиту до ШІ (код {e.code}).")
        except errors.ServerError as e:       # тимчасовий збій на боці Google
            last_error = e
            continue
        except ValidationError:               # модель повернула неправильний формат
            last_error = "invalid-json"
            continue
        except Exception:                     # немає інтернету тощо
            raise AIServiceError("Не вдалося з'єднатися з сервісом ШІ. Спробуйте ще раз.")

    if isinstance(last_error, errors.ClientError) and last_error.code == 429:
        raise AIServiceError("Вичерпано безкоштовний ліміт запитів до ШІ. Спробуйте через хвилину.", 429)
    raise AIServiceError("Сервіс ШІ тимчасово недоступний. Спробуйте пізніше.")


def normalize(result: EmotionResult, model: str) -> dict:
    """Приводить відповідь моделі до відомого списку емоцій і додає емодзі."""
    main = result.emotion.strip().lower()
    if main not in EMOTIONS:
        main = "нейтрально"
    cleaned = (s.strip().lower() for s in result.secondary)
    secondary = [s for s in dict.fromkeys(cleaned) if s in EMOTIONS and s != main][:2]  # без повторів
    return {
        "emotion": main,
        "emoji": EMOTIONS[main],
        "confidence": result.confidence,
        "secondary": [{"emotion": s, "emoji": EMOTIONS[s]} for s in secondary],
        "explanation": result.explanation,
        "advice": result.advice,
        "quote": result.quote,
        "model": model,
    }


@app.get("/")
def index():
    return render_template("index.html", max_len=MAX_LEN)


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()

    # Перевірка вхідних даних
    if not text:
        return jsonify(error="Введіть текст для аналізу."), 400
    if len(text) > MAX_LEN:
        return jsonify(error=f"Текст задовгий: максимум {MAX_LEN} символів."), 400
    if len(text) < 3:
        return jsonify(error="Текст закороткий – напишіть хоча б кілька слів."), 400

    started = time.perf_counter()
    try:
        result = analyze_emotion(text)
    except AIServiceError as e:
        app.logger.warning("AI error: %s", e.message)
        return jsonify(error=e.message), e.status
    result["time_ms"] = int((time.perf_counter() - started) * 1000)
    return jsonify(result)


@app.get("/api/health")
def health():
    return jsonify(status="ok", ai_configured=client is not None, models=MODELS)


@app.errorhandler(404)
def not_found(_):
    return jsonify(error="Сторінку не знайдено."), 404


if __name__ == "__main__":
    if not API_KEY:
        print("УВАГА: ключ Gemini не знайдено. Створіть файл api_key.txt або задайте GEMINI_API_KEY.")
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False)
