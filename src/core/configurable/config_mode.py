import re
import yaml
from pathlib import Path

# Import Stego technique engine
from src.core.stego.lsb_pp import LSBPP
from src.core.stego.locomotive import Locomotive
from src.core.stego.metadata import MetadataEmbedder

# ---- Read & Write Yaml Config ----
def read_yaml(yaml_path: str| Path) -> dict:
    if isinstance(yaml_path, str):
        yaml_path = Path(yaml_path)
        
    return yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

def write_yaml(config_dict: dict, yaml_path: str | Path):
    Path(yaml_path).write_text(
        yaml.safe_dump(config_dict, allow_unicode=True, sort_keys=False),
        encoding="utf-8"
    )

# Resolver: แทนที่ ${{ ... }} รองรับ variables.X และ steps.ID.outputs.KEY[i]
REF_PATTERN = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")
ONE_REF = re.compile(r"^\$\{\{\s*(.*?)\s*\}\}$") # ทั้งค่าเป็น ref เดียว
INDEX = re.compile(r"(\w+)\[(\d+)\]") # key ที่มี index เช่น stego_files[0]

def lookup(path: str, context: dict):
    """เดินตาม path เช่น 'variables.SRC_IMG1' หรือ 'steps.s1.outputs.stego_files[0]'"""
    current_context = context
    for key in path.split("."):
        matched = INDEX.fullmatch(key)
        try:
            current_context = current_context[matched.group(1)][int(matched.group(2))] if matched else current_context[key]
        except (KeyError, IndexError, TypeError):
            raise ValueError(f"Cannot resolve reference '{path}': key not found (make sure the referenced step has run and the key name is correct)")
    return current_context

def resolve_value(value, context: dict):
    """แทนที่ ${{ ... }} ในค่าทุกชนิด (str/list/dict) แบบ recursive"""
    if isinstance(value, str):
        one = ONE_REF.match(value)
        if one:                        # ทั้งค่าเป็น ref เดียว → คืนค่าจริง (คงชนิด list/str)
            return lookup(one.group(1), context)
        return REF_PATTERN.sub(lambda m: str(lookup(m.group(1), context)), value)  # ref กลางสตริง
    if isinstance(value, list):
        return [resolve_value(v, context) for v in value]
    if isinstance(value, dict):
        return {k: resolve_value(v, context) for k, v in value.items()}
    return value

# -- parse encryption config to cryto keyword arguments --
def crypto_kwargs(encryption):
    if not encryption:
        return {}
    mode = encryption["mode"]
    if mode == "symmetric":
        return {"password": encryption["password"]}
    if mode == "asymmetric":
        return {"public_key_path": encryption["public_key"]}
    raise ValueError(f"Unknown encryption mode: {mode!r}")

# พื้นที่ทำงานของ configurable pipeline — output ทุกไฟล์เซฟลงใต้โฟลเดอร์นี้
CONFIG_WORKSPACE = Path(__file__).parent / "config_workspace"

def to_workspace(value):
    """แปลง path string ทุกตัวใน outputs ให้เป็น path จริงใต้ config_workspace + สร้างโฟลเดอร์
    (ทำที่ runner ก่อนเรียก handler → path ที่เก็บใน context เป็นของจริง step ถัดไปอ้างต่อเปิดไฟล์ได้)"""
    if isinstance(value, str):
        full = CONFIG_WORKSPACE / value
        full.parent.mkdir(parents=True, exist_ok=True)
        return str(full)
    if isinstance(value, list):
        return [to_workspace(v) for v in value]
    if isinstance(value, dict):
        return {key: to_workspace(value) for key, value in value.items()}
    return value

# ---- Handle Function ----
def handle_lsbpp(inputs: dict, outputs: dict):
    # LSB++ payload = ข้อความเท่านั้น (text หรืออ่านจากไฟล์ .txt)
    message = inputs.get("text_payload")
    if message is None and inputs.get("text_file"):
        message = Path(inputs["text_file"]).read_text(encoding="utf-8")
    if message is None:
        raise ValueError("LSB++ : must provide text_payload or text_file")

    # embed_stego_bytes = คืน bytes ที่รักษา text chunk เดิม + payload EOF (Locomotive) ไว้
    # LSB++ วางทับชั้นอื่นบนไฟล์เดียวได้โดยไม่ทำลายกัน (ลำดับไม่ถูกบังคับ)
    stego_bytes, _ = LSBPP().embed(
        cover_image_path=inputs["covers"][0], # lsb = ภาพเดียว(หยิบตัวแรก)
        message=message,
        **crypto_kwargs(inputs.get("encryption")),
    )
    save_path = outputs["stego_file"] # เป็น path ใต้ workspace แล้ว (runner แปลงให้)
    Path(save_path).write_bytes(stego_bytes)
    return save_path

def handle_locomotive(inputs: dict, outputs: dict):
    # Locomotive: ฝังไฟล์ (list) หรือ raw_text โดย covers เป็น list และ output เป็น list เสมอ
    results = Locomotive().embed(
        cover_image_paths=inputs["covers"],
        file_paths=inputs.get("file_payload"),
        raw_text=inputs.get("text_payload"),
        **crypto_kwargs(inputs.get("encryption")),
    )  # -> list[(filename, bytes)] ยาวเท่าจำนวน cover

    output_paths = outputs["stego_files"] # list ยาวเท่ากับ covers
    if len(output_paths) != len(results):
        raise ValueError(
            f"Locomotive : must provide output {len(output_paths)} path but engine return {len(results)} files"
        )
    saved = []
    for (_, data), dst in zip(results, output_paths): # dst = path ใต้ workspace แล้ว
        Path(dst).write_bytes(data)
        saved.append(dst)
    return saved

def handle_metadata(inputs: dict, outputs: dict):
    # Metadata: dispatch PNG/MP3 ตามนามสกุล cover เอง · asymmetric ไม่รองรับ
    enc = inputs.get("encryption")
    if enc and enc.get("mode") == "asymmetric":
        raise ValueError("metadata: asymmetric encryption (public key) is not supported")
    password = (enc or {}).get("password") # PNG มองข้าม · MP3 ใช้เข้ารหัสสารบัญ

    return MetadataEmbedder().embed(
        file_path=inputs["covers"][0],
        data=inputs["meta_dict"],
        save_path=outputs["stego_file"], # เป็น path ใต้ workspace แล้ว
        password=password,
    )

MODULE_HANDLERS = {
    "lsbpp": handle_lsbpp,
    "locomotive": handle_locomotive,
    "metadata": handle_metadata,
}

def parse_pipeline(config_dict: dict) -> list:
    return config_dict.get("workflows", {}).get("embed", [])

# ---- Validator: ตรวจ pipeline ก่อนรัน (type / compatibility / references) ----
def extension_type(path: str) -> str:
    """เดาชนิดไฟล์จากนามสกุล → 'png' / 'mp3' / 'unknown'"""
    p = str(path).lower()
    if p.endswith(".png"): return "png"
    if p.endswith(".mp3"): return "mp3"
    return "unknown"

def ref_classify(inner: str):
    """แยกประเภท ref: 'variables.X' → ('var','X') · 'steps.ID.outputs...' → ('step','ID')"""
    head, _, rest = inner.partition(".")
    if head == "variables": return ("var", rest)
    if head == "steps":     return ("step", rest.split(".")[0])
    return ("other", inner)

def cover_target(cover):
    """คืน (kind, value) ของ cover 1 ตัว: ('var',NAME)/('step',STEP_ID)/('literal',path)"""
    if isinstance(cover, str):
        matched = ONE_REF.match(cover)
        if matched:
            kind, value = ref_classify(matched.group(1))
            if kind != "other":
                return (kind, value)
        return ("literal", cover)
    return ("literal", cover)

def cover_type(cover, variables, step_types):
    kind, value = cover_target(cover)
    if kind == "literal": return extension_type(value)
    if kind == "var":     return extension_type(variables.get(value, ""))
    if kind == "step":    return step_types.get(value, "unknown")
    return "unknown"

def validate_pipeline(config_dict: dict) -> list:
    """ตรวจ pipeline ก่อนรัน คืน list ของ (level, step_id, message)
      level = 'error' (บล็อกการรัน) | 'warn' (รันได้ แต่ควรรู้)
    ครอบคลุม: module/ref ถูกต้อง · payload+cover type ต่อ module · encryption · เตือน LSB++ ซ้ำ
    (กฎ 'Locomotive ต้องเป็นตัวสุดท้าย' ถูกยกเลิกแล้ว — LSB++/Meta-PNG preserve payload EOF ได้)"""
    variables = config_dict.get("variables", {})
    issues = []
    step_types = {} # step_id -> ชนิด output ('png'/'mp3')
    step_modules = {} # step_id -> module
    seen = set()

    def err(step_id, message): issues.append(("error", step_id, message))
    def warn(step_id, message): issues.append(("warn", step_id, message))

    for step in parse_pipeline(config_dict):
        step_id = step.get("step_id", "<no-id>")
        module = step.get("module")
        inputs = step.get("inputs", {})
        
        # Step ID ซ้ำจะ error
        if step_id in seen: err(step_id, "duplicate step_id")
        
        seen.add(step_id)
        if module not in MODULE_HANDLERS:
            err(step_id, f"unknown module: {module!r}")
            continue

        # 1) references ต้องชี้ของที่มีจริง + step ต้องอยู่ก่อนหน้า (backward-only)
        for ref in REF_PATTERN.findall(str(inputs)) + REF_PATTERN.findall(str(step.get("outputs", {}))):
            kind, value = ref_classify(ref.strip())
            if kind == "var" and value not in variables:
                err(step_id, f"references a variable that doesn't exist: variables.{value}")
            elif kind == "step" and value not in step_types:
                err(step_id, f"references a step that hasn't run yet / doesn't exist: steps.{value} (must be defined earlier)")

        # 2) covers ต้องเป็น list
        covers = inputs.get("covers")
        if not isinstance(covers, list) or not covers:
            err(step_id, "covers must be a list with at least 1 file")
            covers = []
        cover_types = [cover_type(cover, variables, step_types) for cover in covers]

        # 3) encryption
        encryption = inputs.get("encryption")
        if encryption:
            mode = encryption.get("mode")
            if mode == "symmetric" and not encryption.get("password"):
                err(step_id, "symmetric encryption requires a password")
            elif mode == "asymmetric" and not encryption.get("public_key"):
                err(step_id, "asymmetric encryption requires a public_key")
            elif mode not in ("symmetric", "asymmetric"):
                err(step_id, f"invalid encryption.mode: {mode!r}")

        # 4) กฎเฉพาะ module + ชนิด output
        if module == "lsbpp":
            if not (inputs.get("text_payload") or inputs.get("text_file")):
                err(step_id, "lsbpp: requires text_payload or text_file (LSB++ only accepts text)")
            if inputs.get("file_payload"):
                err(step_id, "lsbpp: cannot embed files (use text_payload/text_file)")
            if "mp3" in cover_types:
                err(step_id, "lsbpp: cover must be PNG (found MP3)")
            for cover in covers:  # เตือน LSB++ ซ้ำบน output ของ lsbpp เดิม (เสี่ยงทับกัน)
                kind, value = cover_target(cover)
                if kind == "step" and step_modules.get(value) == "lsbpp":
                    warn(step_id, "LSB++ is being stacked on another LSB++ output → risk of corrupting the earlier payload (not yet supported)")
            step_types[step_id] = "png"

        elif module == "locomotive":
            if not (inputs.get("file_payload") or inputs.get("text_payload")):
                err(step_id, "locomotive: requires file_payload or text_payload")
            if "mp3" in cover_types:
                err(step_id, "locomotive: cover must be PNG (found MP3)")
            step_types[step_id] = "png"

        elif module == "metadata":
            meta_dict = inputs.get("meta_dict")
            if not meta_dict:
                err(step_id, "metadata: requires meta_dict")
            if encryption and encryption.get("mode") == "asymmetric":
                err(step_id, "metadata: asymmetric encryption (public key) is not supported")
            # อย่าตั้งชื่อ local ว่า cover_type จะบัง (shadow) ฟังก์ชัน cover_type() ที่ใช้ด้านบน
            first_cover_type = cover_types[0] if cover_types else "unknown"
            if first_cover_type == "unknown":
                warn(step_id, "metadata: could not determine cover type (should be .png or .mp3)")
            if first_cover_type == "png" and isinstance(meta_dict, dict) and "APIC" in meta_dict:
                err(step_id, "metadata PNG: cannot set APIC (image) — PNG only supports text (use MP3)")
            step_types[step_id] = first_cover_type

        step_modules[step_id] = module

    return issues


def run_embed_pipeline(config_dict: dict) -> dict:
    # ตรวจก่อนรัน เจอ error = ไม่รันต่อ
    issues = validate_pipeline(config_dict)
    for level, step_id, message in issues:
        print(f"[{level.upper()}] {step_id}: {message}")
    if any(level == "error" for level, _, _ in issues):
        raise ValueError(f"Pipeline validation failed ({sum(1 for i in issues if i[0]=='error')} error(s)) — see the errors printed above")

    # context = memory ระหว่างรัน: เก็บ variables + output ของ step ที่รันไปแล้ว
    context = {"variables": config_dict.get("variables", {}), "steps": {}}
    for step in parse_pipeline(config_dict):
        step_id, module = step["step_id"], step["module"]
        handler = MODULE_HANDLERS.get(module)
        if handler is None:
            raise ValueError(f"Unknown module {module!r} in step {step_id!r}")

        inputs = resolve_value(step["inputs"], context)
        outputs = to_workspace(resolve_value(step["outputs" ], context))  # path จริงใต้ workspace
        print(f"[STEP] {step_id} (module={module})")
        handler(inputs, outputs)
        context["steps"][step_id] = {"outputs": outputs}  # ให้ step ถัดไปอ้าง ${{ steps.ID.outputs.KEY }}
    return context["steps"]


# =========================================================================
# Extract pipeline — reverse ของ embed + จัดลำดับด้วย topological sort
# แต่ละ embed step กลับด้านเป็น extract step: needs = ไฟล์ที่ต้องมีก่อนแกะ,
# provides = payload ที่แกะได้ (อาจเป็นไฟล์ stego ชั้นในที่ step อื่นต้องใช้ต่อ)
# 2 รูปแบบการซ้อน:
#   cover chaining   : A.output เป็น cover ของ B → A อยู่ในไฟล์เดียวกับ B (แกะจากไฟล์ B)
#   payload chaining : A.output เป็น payload ของ B → ต้องแกะ B ก่อนเพื่อกู้ไฟล์ A ออกมา แล้วค่อยแกะ A
# =========================================================================
def ref_step(value):
    """ถ้า value เป็น ${{ steps.ID.outputs... }} คืน ID ไม่งั้น None"""
    if isinstance(value, str):
        m = ONE_REF.match(value)
        if m and ref_classify(m.group(1))[0] == "step":
            return ref_classify(m.group(1))[1]
    return None

def _cover_producers(inputs: dict) -> set:
    return {p for c in inputs.get("covers", []) if (p := ref_step(c))}

def _payload_producers(inputs: dict) -> set:
    """step ที่ถูกอ้างใน inputs แต่ไม่ใช่ cover = ถูกเอาไปเป็น payload"""
    refs = {ref_classify(r)[1] for r in REF_PATTERN.findall(str(inputs)) if ref_classify(r)[0] == "step"}
    return refs - _cover_producers(inputs)

def deliverable_step_ids(config_dict: dict) -> list:
    """step_id ของไฟล์ 'ผลลัพธ์สุดท้าย' — output ที่ไม่ถูก step ไหน consume ต่อ (ไฟล์ที่ผู้ใช้ส่งจริง)"""
    embed = parse_pipeline(config_dict)
    consumed = set()
    for s in embed:
        inp = s.get("inputs", {})
        consumed |= _cover_producers(inp) | _payload_producers(inp)
    return [s["step_id"] for s in embed if s["step_id"] not in consumed]

def generate_extract_pipeline(config_dict: dict) -> list:
    """คืน list ของ extract-node (จัดลำดับแล้วพร้อมรัน) จาก embed workflow

    resource ของไฟล์ใช้รูปแบบ `file:STEP#i` (i = index ของ output) เพื่อรองรับ Locomotive
    ที่มีหลาย cover → หลาย output: cover ตำแหน่ง i อยู่ในไฟล์ output ตำแหน่ง i (positional)
    และตอนแกะ Locomotive payload ต้องใช้ไฟล์ output 'ครบทุกใบ' (payload กระจายเป็น fragment)"""
    embed = parse_pipeline(config_dict)
    by_id = {s["step_id"]: s for s in embed}

    def n_outputs(sid):
        value = next(iter(by_id[sid].get("outputs", {}).values()), None)
        return len(value) if isinstance(value, list) else 1

    consumed_as_cover = {}    # producer_id -> (consumer_id, cover_position)
    consumed_as_payload = {}  # producer_id -> consumer_id
    for s in embed:
        inp = s.get("inputs", {})
        for pos, cover in enumerate(inp.get("covers", [])):
            if (p := ref_step(cover)):
                consumed_as_cover[p] = (s["step_id"], pos)
        for p in _payload_producers(inp):
            consumed_as_payload[p] = s["step_id"]

    def carrier(cid, out_pos):
        """resource ของ 'ไฟล์จริงชั้นนอกสุด' ที่บรรจุ output[out_pos] ของ step cid
        — output[0] อาจถูกใช้เป็น cover ของ step อื่นต่อ (ref ชี้ stego_files[0]) จึงไล่ต่อ
        ส่วน output[>0] อ้างต่อไม่ได้ → เป็นไฟล์จริงในตัวมันเอง"""
        if out_pos == 0 and cid in consumed_as_cover:
            consumer, pos = consumed_as_cover[cid]
            return carrier(consumer, pos)
        return f"file:{cid}#{out_pos}"

    nodes = []
    for s in embed:
        sid = s["step_id"]
        pp = _payload_producers(s.get("inputs", {}))
        # ถ้า payload คือ output ของ step X → แกะแล้วได้ไฟล์ X (recovered:X) ให้ step ถัดไปใช้
        provides = f"recovered:{next(iter(pp))}" if pp else f"payload:{sid}"

        if sid in consumed_as_payload:
            needs = [f"recovered:{sid}"]                                   # output เป็นไฟล์ payload ชั้นใน — ต้องแกะ consumer ก่อน
        elif s["module"] == "locomotive":
            needs = [carrier(sid, i) for i in range(n_outputs(sid))]       # Locomotive ต้องมี fragment ครบทุกไฟล์
        else:
            needs = [carrier(sid, 0)]

        node = {"step_id": f"ext_{sid}", "embed_id": sid, "module": s["module"],
                "needs": needs, "provides": [provides]}
        enc = s.get("inputs", {}).get("encryption")
        if enc:
            node["decrypt"] = {"mode": enc["mode"]}   # บอกว่า step นี้เข้ารหัสแบบไหน (ผู้รับต้องกรอก password/private key เอง — ไม่เก็บ secret ลงไฟล์)
        nodes.append(node)

    # ทรัพยากรตั้งต้น = ไฟล์ output ที่ไม่ถูก consume (per-file: output[0] ถูก consume ได้, output[>0] ไม่)
    available = set()
    for s in embed:
        sid = s["step_id"]
        for i in range(n_outputs(sid)):
            consumed = i == 0 and (sid in consumed_as_cover or sid in consumed_as_payload)
            if not consumed:
                available.add(f"file:{sid}#{i}")

    ordered, pending = [], list(nodes)
    while pending:
        run = next((n for n in pending if set(n["needs"]) <= available), None)
        if run is None:
            raise ValueError(f"extract deadlock: {[n['step_id'] for n in pending]}")
        ordered.append(run)
        available.update(run["provides"])
        pending.remove(run)
    return ordered


# ---- Extract execution ----
def decrypt_kwargs(encryption, private_key_path=None) -> dict:
    """encryption ตอน embed → kwargs สำหรับ .extract() (สลับ public_key → private_key)"""
    if not encryption:
        return {}
    if encryption["mode"] == "symmetric":  return {"password": encryption["password"]}
    if encryption["mode"] == "asymmetric": return {"private_key_path": private_key_path}
    return {}

def _output_list(outputs: dict) -> list:
    """path ทุกไฟล์จาก outputs ตามลำดับ (stego_file เดี่ยว หรือ stego_files เป็น list)"""
    value = next(iter(outputs.values()))
    return value if isinstance(value, list) else [value]

def run_extract_pipeline(config_dict: dict, embed_results: dict, private_key_path: str = None) -> dict:
    """รัน extract ตามลำดับที่ topological-sort ให้ คืน dict ของ resource → payload ที่กู้ได้
    embed_results: {step_id: {"outputs": {...}}} — ต้องมีอย่างน้อยไฟล์ deliverable ที่ผู้รับถืออยู่"""
    by_id = {s["step_id"]: s for s in parse_pipeline(config_dict)}
    out_dir = CONFIG_WORKSPACE / "extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    # resource file:STEP#i → path ไฟล์จริงตัวที่ i (เริ่มจาก deliverable ที่ผู้รับมี)
    res_path = {}
    for sid, r in embed_results.items():
        for i, path in enumerate(_output_list(r["outputs"])):
            res_path[f"file:{sid}#{i}"] = path
    recovered = {}

    for node in generate_extract_pipeline(config_dict):
        eid, module, provide = node["embed_id"], node["module"], node["provides"][0]
        sources = [res_path[n] for n in node["needs"]]   # Locomotive อาจต้องหลายไฟล์ (fragment ครบ)
        kw = decrypt_kwargs(by_id[eid]["inputs"].get("encryption"), private_key_path)
        print(f"[EXT] {node['step_id']} (module={module}) <- {[Path(s).name for s in sources]}")

        if module == "lsbpp":
            recovered[provide] = LSBPP().extract(sources[0], **kw)
        elif module == "locomotive":
            name, data = Locomotive().extract(sources, **kw)   # ส่ง fragment ครบทุกไฟล์
            dst = out_dir / f"{eid}_{name}"
            dst.write_bytes(data)
            res_path[provide] = str(dst)     # ไฟล์ stego ชั้นในที่กู้ได้ ให้ step ถัดไปแกะต่อ
            recovered[provide] = str(dst)
        elif module == "metadata":
            recovered[provide] = MetadataEmbedder().extract(sources[0], password=kw.get("password"))

    return recovered


# =========================================================================
# Extract จาก extract_config.yaml ล้วนๆ (self-contained) — สำหรับหน้า Extract ฝั่งผู้รับ
# ผู้รับมีแค่ไฟล์ deliverable + extract config · password/private-key กรอกตอนรัน (ไม่อยู่ในไฟล์)
# =========================================================================
def extract_nodes(extract_config: dict) -> list:
    return extract_config.get("workflows", {}).get("extract", [])

def required_resources(extract_config: dict) -> list:
    """resource ตั้งต้นที่ผู้รับต้องอัปโหลด = file:X#i ที่ถูก 'needs' แต่ไม่มีใคร 'provides'
    คืน list ของ (resource_id, suggested_filename) เรียงตามที่เจอครั้งแรก"""
    nodes = extract_nodes(extract_config)
    provided = {p for n in nodes for p in n.get("provides", [])}
    hints = extract_config.get("resources", {})
    seen, result = set(), []
    for n in nodes:
        for res in n.get("needs", []):
            if res not in provided and res not in seen:
                seen.add(res)
                result.append((res, hints.get(res, res)))
    return result

def _decrypt_kwargs_from_node(decrypt: dict, secret: dict) -> dict:
    """decrypt info ต่อ node (mode) + secret ที่ผู้รับกรอก → kwargs ของ .extract()"""
    if not decrypt:
        return {}
    if decrypt["mode"] == "symmetric":
        return {"password": secret.get("password")}
    if decrypt["mode"] == "asymmetric":
        return {"private_key_path": secret.get("private_key_path")}
    return {}

def run_extract_from_config(extract_config: dict, resource_files: dict, secrets: dict = None) -> dict:
    """รัน extract จาก extract_config ล้วนๆ (ไม่ต้องมี embed config)
    resource_files: {resource_id (file:X#i) -> path ไฟล์ที่ผู้รับอัปโหลด}
    secrets: {embed_id -> {"password": ...} หรือ {"private_key_path": ...}} สำหรับ step ที่เข้ารหัส"""
    secrets = secrets or {}
    out_dir = CONFIG_WORKSPACE / "extract"
    out_dir.mkdir(parents=True, exist_ok=True)

    res_path = dict(resource_files)   # เริ่มจากไฟล์ที่ผู้รับมี ; recovered:X จะถูกเติมระหว่างแกะ
    recovered = {}
    for node in extract_nodes(extract_config):
        eid, module, provide = node["embed_id"], node["module"], node["provides"][0]
        sources = [res_path[n] for n in node["needs"]]
        kw = _decrypt_kwargs_from_node(node.get("decrypt"), secrets.get(eid, {}))
        print(f"[EXT] {node['step_id']} (module={module}) <- {[Path(s).name for s in sources]}")

        if module == "lsbpp":
            recovered[provide] = LSBPP().extract(sources[0], **kw)
        elif module == "locomotive":
            name, data = Locomotive().extract(sources, **kw)
            dst = out_dir / f"{eid}_{name}"
            dst.write_bytes(data)
            res_path[provide] = str(dst)
            recovered[provide] = str(dst)
        elif module == "metadata":
            recovered[provide] = MetadataEmbedder().extract(sources[0], password=kw.get("password"))

    return recovered

if __name__ == '__main__':
    
    config_dict = {
        "variables": {
            "SRC_IMG1": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/img/001.png",
            "SRC_IMG2": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/img/002.png",
            "SRC_IMG3": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/img/003.png",
            "SRC_IMG4": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/img/004.png",
            "SRC_MP3": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/audio/001.mp3",

            "RECEIVER_PUB_KEY": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/yaml/data/pub_key.pem",

            "PAYLOAD_TEXT": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/data/payload.txt",
            "PAYLOAD_FILE": "D:/SRY-DEV/cs-project/Program/Doing/GUI/SIENG2/src/core/configurable/cross_media.yaml"
        },
        "workflows": {
            "embed": [
                # 1) LSB++ + ข้อความ + เข้ารหัส symmetric (password)
                {
                    "step_id": "lsbpp_embed_txt_in_png",
                    "module": "lsbpp",
                    "inputs": {
                        "covers": ["${{ variables.SRC_IMG1 }}"],
                        "text_payload": "TEST1",
                        "encryption": {
                            "mode": "symmetric",
                            "password": "123"
                        }
                    },
                    "outputs": {
                        "stego_file": "output/001_stego.png"
                    }
                },
                # 2) LSB++ + อ่านข้อความจากไฟล์ .txt + เข้ารหัส asymmetric (public key)
                {
                    "step_id": "lsbpp_embed_txt_in_png_1",
                    "module": "lsbpp",
                    "inputs": {
                        "covers": ["${{ variables.SRC_IMG2 }}"],
                        "text_file": "${{ variables.PAYLOAD_TEXT }}",
                        "encryption": {
                            "mode": "asymmetric",
                            "public_key": "${{ variables.RECEIVER_PUB_KEY }}"
                        }
                    },
                    "outputs": {
                        "stego_file": "output/002_stego.png"
                    }
                },
                # 3) Locomotive + ฝัง "ไฟล์" (list) + เข้ารหัส asymmetric
                {
                    "step_id": "loco_embed_file_in_png",
                    "module": "locomotive",
                    "inputs": {
                        "covers": ["${{ variables.SRC_IMG3 }}"],
                        "file_payload": ["${{ variables.PAYLOAD_FILE }}"],
                        "encryption": {
                            "mode": "asymmetric",
                            "public_key": "${{ variables.RECEIVER_PUB_KEY }}"
                        }
                    },
                    "outputs": {
                        "stego_files": ["output/003_loco.png"]
                    }
                },
                # 4) Metadata (PNG) — iTXt text chunks (ไม่มี encryption)
                {
                    "step_id": "meta_embed_text_in_png",
                    "module": "metadata",
                    "inputs": {
                        "covers": ["${{ variables.SRC_IMG4 }}"],
                        "meta_dict": {
                            "Title": "TEST",
                            "SIENG2": "GOD"
                        }
                    },
                    "outputs": {
                        "stego_file": "output/004_metadata.png"
                    }
                },
                # 5) Metadata (MP3) — ID3 frames
                {
                    "step_id": "meta_embed_text_in_mp3",
                    "module": "metadata",
                    "inputs": {
                        "covers": ["${{ variables.SRC_MP3 }}"],
                        "meta_dict": {
                            "TIT2": "test_title",
                            "TDRC": "2018",
                            "COMM": [
                                {
                                    "lang": "eng",
                                    "desc": "test_desc",
                                    "text": "test_text"
                                }
                            ],
                            "TXXX": [
                                {
                                    "desc": "Encoded by",
                                    "text": "LAME in FL Studio 20"
                                }
                            ]
                        }
                    },
                    "outputs": {
                        "stego_file": "output/001_metadata.mp3"
                    }
                },
                # 6) CHAINING — LSB++ ทับบน output ของ Locomotive (step 3)
                #    พิสูจน์: ${{ steps.X.outputs.Y[i] }} ใช้ได้ + Locomotive ไม่ต้องเป็นตัวสุดท้าย
                #    (LSB++ preserve payload EOF ของ loco ไว้ → ถอดได้ทั้งสองชั้น)
                {
                    "step_id": "lsbpp_over_loco",
                    "module": "lsbpp",
                    "inputs": {
                        "covers": ["${{ steps.loco_embed_file_in_png.outputs.stego_files[0] }}"],
                        "text_payload": "STACKED ON LOCO",
                        "encryption": {
                            "mode": "symmetric",
                            "password": "pw"
                        }
                    },
                    "outputs": {
                        "stego_file": "output/006_lsb_over_loco.png"
                    }
                }
            ]
        }
    }
    
    yaml_file = Path(__file__).parent / 'cross_media.yaml'
    run_embed_pipeline(config_dict)
    write_yaml(config_dict, r"D:\SRY-DEV\cs-project\Program\Doing\GUI\SIENG2\src\core\configurable\config_workspace\output\config.yaml")