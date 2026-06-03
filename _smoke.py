"""Smoke test for codex config_server.py — focus on save_provider toml + wire_api"""
import time, threading, urllib.request, urllib.error, json, sys, tempfile, os, shutil
import importlib.util

# Use a temp data dir so we don't clobber real config
spec = importlib.util.spec_from_file_location('cs', 'lib/config_server.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Redirect data dir to temp
tmp = tempfile.mkdtemp()
from pathlib import Path
m.DATA_DIR = Path(tmp)
m.CCS_DIR = Path(tmp) / ".cc-switch"
m.CCS_DB = m.CCS_DIR / "cc-switch.db"

errors = []
def check(name, cond, detail=""):
    print(f"  {'[OK]' if cond else '[!!]'} {name}" + (f": {detail}" if not cond else ""))
    if not cond: errors.append(name)

# 1. save a DeepSeek (non-openai) provider -> wire_api should be "chat"
m.save_provider("DeepSeek", "https://api.deepseek.com/v1", "sk-test1234567890", "deepseek-v4-pro")
toml = (Path(tmp) / ".codex" / "config.toml").read_text()
check("deepseek wire_api=chat", 'wire_api = "chat"' in toml, toml)
check("deepseek model written", 'deepseek-v4-pro' in toml)

# 2. save an OpenAI provider -> wire_api should be "responses" (only model line)
m.save_provider("OpenAI", "https://api.openai.com/v1", "sk-test1234567890", "gpt-5.5")
toml2 = (Path(tmp) / ".codex" / "config.toml").read_text()
check("openai uses model line", 'model = "gpt-5.5"' in toml2)

# 3. toml escape: malicious name with quote
m.save_provider('Ev"il', "https://api.groq.com/openai/v1", "gsk_test1234567890", 'mod"el')
toml3 = (Path(tmp) / ".codex" / "config.toml").read_text()
check("groq wire_api=chat", 'wire_api = "chat"' in toml3)
check("toml escapes quotes", '\\"' in toml3, toml3)
# verify it's parseable as TOML if tomllib available
try:
    import tomllib
    parsed = tomllib.loads(toml3)
    check("escaped toml parses", True)
except ImportError:
    check("escaped toml parses (tomllib N/A, skipped)", True)
except Exception as e:
    check("escaped toml parses", False, str(e))

# 4. auth.json written with key
auth = json.loads((Path(tmp) / ".codex" / "auth.json").read_text())
check("auth.json has key", auth.get("OPENAI_API_KEY") == "gsk_test1234567890")

# 5. read_current returns the saved provider
cur = m.read_current()
check("read_current works", cur is not None and cur.get("base_url"))

# 6. start server, test endpoints
srv_mod = m
from http.server import ThreadingHTTPServer
srv = ThreadingHTTPServer(('127.0.0.1', 17593), m.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.3)
H={'Host':'127.0.0.1:17593'}; tok=m.SERVER_TOKEN
def post(path,body,t=True):
    h={**H,'Content-Type':'application/json'}
    if t: h['X-CC-Token']=tok
    req=urllib.request.Request(f'http://127.0.0.1:17593{path}',data=json.dumps(body).encode(),method='POST',headers=h)
    try:
        r=urllib.request.urlopen(req); return json.loads(r.read()),r.status
    except urllib.error.HTTPError as e: return json.loads(e.read()),e.code

lc,code=post('/api/launch-ccswitch',{})
check("launch-ccswitch endpoint", 'ok' in lc and 'message' in lc)
_,c=post('/api/save',{'name':'x','base_url':'https://x.com','api_key':'k'*8,'model':''},t=False)
check("CSRF blocks no-token", c==403)
st=json.loads(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:17593/api/state',headers=H)).read())
check("providers >= 11", len(st['providers_catalog'])>=11, str(len(st['providers_catalog'])))

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("="*40)
if errors:
    print(f"FAILED {len(errors)}: {errors}"); sys.exit(1)
print("ALL PASSED")
