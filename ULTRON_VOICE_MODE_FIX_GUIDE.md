# ULTRON — Voice Mode Full Fix Guide

Ye file tumhare **khud se voice mode fix karne** ke liye hai. Har section mein:
`Problem → Kaunsi file → Kya dikhega → Kya change karna hai`

Voice mode ka poora flow 4 files control karte hain:

```
config.py                        -> saare voice-related numbers/settings yahan hain
voice/microphone/microphone.py   -> mic kab tak sunta hai, kab rukta hai
voice/wakeword/detector.py       -> "Ultron" wake word detect karta hai
core/assistant.py -> run_listen()-> poora conversation loop (wake -> command -> reply -> next)
```

---

## ✅ FIX #1 (already applied) — "Reply ke baad phir se Ultron bolna padta tha"

**Problem:** Ek command ka jawab milne ke baad Ultron seedha wapas "sirf wake-word sununga" mode mein chala jaata tha. Har naye command ke liye "Ultron" bolna zaroori tha.

**File:** `core/assistant.py` → `run_listen()`

**Kya kiya gaya:**
- Reply dene ke baad ab ek `listen_for_followups()` loop chalta hai jo **bina wake word ke** seedha agla command sunta hai.
- `config.py` mein naya setting add hua:
  ```python
  FOLLOWUP_LISTEN_TIMEOUT = _env_float("FOLLOWUP_LISTEN_TIMEOUT", 6.0)
  ```
  Matlab: reply ke baad 6 second tak chup rahoge to hi wapas "Ultron" bolna padega. Isse pehle bolo to bina wake word turant sun lega.
- "go to sleep" / "stop listening" / "that's all" bolne se turant wapas wake-word mode mein chala jaata hai (6 sec wait kiye bina).

**Agar tumhe ye khud tune karna hai:**
| Kya chahiye | Kahan | Value badlo |
|---|---|---|
| Follow-up window lamba karo (zyada der tak bina "Ultron" sun le) | `config.py` | `FOLLOWUP_LISTEN_TIMEOUT` ko 6.0 se 10-15 karo |
| Follow-up window chota karo (jaldi wake-word mode mein wapas) | `config.py` | `FOLLOWUP_LISTEN_TIMEOUT` ko 3-4 karo |
| Kaunse words se conversation turant end ho | `core/assistant.py` | `_SLEEP_PHRASES` tuple mein words add/remove karo |

**Status:** ✅ Ye already fix ho chuka hai project mein.

---

## ⚠️ FIX #2 — "Main pura bolta hoon lekin Ultron beech mein hi sunna band kar deta hai"

Ye sabse common voice-mode complaint hai. Iske **3 alag causes** ho sakte hain — sabko check karo.

### Cause A: `MIC_PAUSE_THRESHOLD` bahut kam hai
**File:** `config.py`
```python
MIC_PAUSE_THRESHOLD = _env_float("MIC_PAUSE_THRESHOLD", 0.8)   # silence -> phrase end
```
Ye batata hai ki kitni der ki **chup (silence)** ke baad Jarjis maan le ki tumne bolna khatam kar diya. Agar tum bolte waqt beech mein ek second ruk jaate ho (sochne ke liye, ya "aur... um... ye wala kaam karo" jaisa), to 0.8 second se zyada ruke to Ultron wahin kaat dega.

**Fix:** Value badhao:
```python
MIC_PAUSE_THRESHOLD = _env_float("MIC_PAUSE_THRESHOLD", 1.2)
```
1.0–1.5 range try karo. Zyada high (2+) karoge to reply thoda slow lagega kyunki har baar utni der wait karega.

### Cause B: `non_speaking_duration` mic file mein hardcoded hai
**File:** `voice/microphone/microphone.py`
```python
self.recognizer.non_speaking_duration = min(0.3, MIC_PAUSE_THRESHOLD)
```
Ye `MIC_PAUSE_THRESHOLD` se bhi chota rakha gaya hai (max 0.3s). Agar tum upar `MIC_PAUSE_THRESHOLD` badhaate ho, ye khud-ba-khud thoda badhega (kyunki `min()` use ho raha hai) lekin 0.3 se zyada kabhi nahi jayega jab tak tum ye line khud na badlo.

**Fix (agar chahiye ki isse bhi zyada ho):**
```python
self.recognizer.non_speaking_duration = min(0.5, MIC_PAUSE_THRESHOLD)
```

### Cause C: `COMMAND_PHRASE_TIME_LIMIT` command ko beech mein hi kaat raha hai
**File:** `config.py`
```python
COMMAND_PHRASE_TIME_LIMIT = _env_float("COMMAND_PHRASE_TIME_LIMIT", 15.0)
```
Ye **poore command ki max length** hai (15 second). Agar tum lamba command bolte ho (jaise ek paragraph jaisa instruction), to 15 sec ke baad wo record karna band kar dega — chahe tum abhi bhi bol rahe ho.

**Fix:** Agar lambe commands bolte ho, isko badhao:
```python
COMMAND_PHRASE_TIME_LIMIT = _env_float("COMMAND_PHRASE_TIME_LIMIT", 25.0)
```

### Cause D: Wake-word ke saath bola gaya command khud wake-word detector cut kar raha hai
**File:** `config.py`
```python
WAKE_PHRASE_TIME_LIMIT = _env_float("WAKE_PHRASE_TIME_LIMIT", 4.0)
```
Agar tum "Ultron, mera ye poora kaam karo..." bolte ho sab ek saath, to wake-word wala engine sirf 4 second tak hi sunta hai us combined phrase ko (ye tab apply hota hai jab `WAKE_WORD_ENGINE=stt` legacy engine set ho — naya openWakeWord engine `""` return karta hai aur alag se command sunta hai, jisme `COMMAND_LISTEN_TIMEOUT`/`COMMAND_PHRASE_TIME_LIMIT` lagta hai, Cause C wala).

**Check karo pehle** `.env` ya `config.py` mein `WAKE_WORD_ENGINE` kya set hai:
```python
grep -n "WAKE_WORD_ENGINE" config.py
```
- Agar `stt` hai → `WAKE_PHRASE_TIME_LIMIT` badhao (jaise 6-8).
- Agar openWakeWord (default) hai → ye cause apply nahi hota, Cause C dekho.

---

## ⚠️ FIX #3 — "Command sunne se pehle bahut jaldi timeout ho jaata hai" (kuch bolne se pehle hi "didn't catch that")

**File:** `config.py`
```python
COMMAND_LISTEN_TIMEOUT = _env_float("COMMAND_LISTEN_TIMEOUT", 5.0)
```
Ye batata hai ki "Yes, Sir?" ke baad kitni der tak wo tumhare bolna **shuru karne** ka wait karega. Agar tum thoda deri se bolna start karte ho (soch ke), to 5 sec kam pad sakta hai.

**Fix:**
```python
COMMAND_LISTEN_TIMEOUT = _env_float("COMMAND_LISTEN_TIMEOUT", 8.0)
```

---

## ⚠️ FIX #4 — "Wake word ('Ultron') sunta hi nahi / bahut der lagti hai pakadne mein"

**File:** `config.py` — ye 3 values check karo:
```python
WAKE_WORD_THRESHOLD      # kitna confident hona chahiye "Ultron" sunne ke liye
WAKE_WORD_SMOOTH_FRAMES  # kitne audio frames milaake average nikalta hai
WAKE_WORD_MIC_GAIN       # mic ki awaaz kitni boost karta hai
```
- **Bahut kam sunta hai / miss karta hai** → `WAKE_WORD_THRESHOLD` thoda kam karo (jaise 0.5 → 0.4), ya `WAKE_WORD_MIC_GAIN` badhao agar mic dheema hai.
- **Bar-bar galti se activate ho jaata hai** (koi aur awaaz par bhi) → `WAKE_WORD_THRESHOLD` badhao (jaise 0.5 → 0.6-0.7).

**Debug tool already hai project mein:** `tools/wakeword_debug.py` — isse run karke live scores dekh sakte ho ki tumhara mic kitna confident score de raha hai "Ultron" bolne par. Usi se sahi threshold decide karo.

---

## ⚠️ FIX #5 — "Ultron apni khud ki awaaz sun ke phir se activate ho jaata hai" (self-trigger loop)

Ye tab hota hai jab TTS speaker se awaaz nikalti hai aur wahi mic wapas pick kar leta hai.

**File:** `voice/wakeword/detector.py` — dekh lo `listen_loop()` mein mic stream `on_detected()` ke time **stop** ho raha hai ya nahi (already isme handle hai — comment padhna: *"Two simultaneous open audio streams... this is what caused the stuck symptom"*). Ye already sahi hai is codebase mein.

Agar phir bhi ho raha hai:
- Headphones/earphones use karo (best fix, mic-speaker overlap hi khatam)
- Ya `voice/noise_cancellation.py` mein echo-cancellation check karo agar wo module hai

---

## 🔧 Quick Reference — Sabse zyada tune hone waale config values

| Setting | File | Default | Badhao agar... | Ghatao agar... |
|---|---|---|---|---|
| `MIC_PAUSE_THRESHOLD` | config.py | 0.8 | beech mein ruk jaate ho bolte waqt | reply slow lagta hai |
| `COMMAND_PHRASE_TIME_LIMIT` | config.py | 15.0 | lambe commands bolte ho | — |
| `COMMAND_LISTEN_TIMEOUT` | config.py | 5.0 | bolna start karne mein deri lagti hai | — |
| `WAKE_PHRASE_TIME_LIMIT` | config.py | 4.0 | (sirf legacy STT wake-engine) wake+command ek saath bolte ho | — |
| `FOLLOWUP_LISTEN_TIMEOUT` | config.py | 6.0 (naya) | multi-turn conversation lamba chahiye | jaldi wake-word mode chahiye |
| `WAKE_WORD_THRESHOLD` | config.py | ~0.5 | wake word miss hota hai | galat activation hota hai |

---

## Testing karne ka tareeka har change ke baad

1. `config.py` mein value badlo, save karo.
2. `python main.py` chalao (default hands-free mode).
3. "Ultron" bolo, ruk ke dekho "Yes, Sir?" aaya ya nahi.
4. Ek command bolo jisme beech mein 1 second ruko — check karo pura sunta hai ya kaat deta hai.
5. Reply milne ke baad, bina "Ultron" bole, seedha next command bolo — check karo follow-up mode kaam kar raha hai.
6. Agar sahi laga, ek aur real scenario try karo (lamba command, jaldi bolna, etc.) before finalizing values.

Ek baar mein sirf **ek value** badlo aur test karo — sab kuch ek saath badloge to pata nahi chalega kaunsa fix kaam kar raha hai.
