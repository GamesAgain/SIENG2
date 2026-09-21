# Linked Output — ข้อตกลงและแผนพัฒนา Configurable Pipeline

อัปเดต: 2026-09-21
ตรวจโค้ดบน checkpoint: `62bf165` — `prototype: add immutable pipeline run request boundary`
สถานะงาน: L6 Metadata Linked Output และ L7 Main three-step GUI/Draft acceptance ปิดครบแล้ว;
LSB Cover, Locomotive Covers/File Payload, Metadata Cover/APIC พร้อม picker, persistence,
dependency, single-consumer, BLOCKED และ lifecycle verification
L8.0 Execution Contract ถึง L8.3 Runtime foundation และ L8.4A-L8.4D real adapters ปิดแล้ว;
งานถัดไปคือ L8.5 sequential executor และ run lifecycle

## วิธีใช้เอกสารนี้ร่วมกัน

- ผู้ใช้แก้เอกสารนี้ได้โดยตรง เพื่อปรับความต้องการและลำดับงาน
- ก่อนวิเคราะห์หรือพัฒนา Linked Output แต่ละรอบ ให้อ่านไฟล์นี้ฉบับล่าสุดจาก disk
  และตรวจโค้ดที่เกี่ยวข้อง อย่าอาศัยความจำจากแชทอย่างเดียว
- ถ้าผู้ใช้กล่าวถึงโน้ตเพิ่มเติม เช่น `config_desgin.txt` ให้อ่านด้วย
- คำสั่งล่าสุดของผู้ใช้มีลำดับก่อนเอกสาร หากพบความขัดแย้งที่มีผลต่อแบบ ให้รายงาน
  และทำส่วนที่ไม่ขึ้นกับข้อขัดแย้งก่อน อย่าตัดสินใจเปลี่ยนสถาปัตยกรรมใหญ่เงียบ ๆ
- แยกให้ชัดระหว่าง **โค้ดที่มีแล้ว**, **ข้อตกลง**, และ **ข้อเสนอที่ยังไม่สรุป**
- หลังพัฒนารอบที่ได้รับคำสั่ง ให้อัปเดตสถานะ งานที่ทำจริง ผลตรวจ และงานถัดไปในไฟล์นี้
  รักษาเนื้อหาที่ผู้ใช้แก้ไว้ ไม่เขียนทับทั้งเอกสารจากความจำ
- Checklist เป็นแผน ไม่ใช่คำอนุญาตให้ทำทุกข้อทันที ทำตามขอบเขตที่ผู้ใช้สั่งแต่ละรอบ
- ใช้เอกสารนี้ต่อจน Linked workflow เสร็จ แล้วค่อยระบุว่าเสร็จหรือย้ายเป็นเอกสารถาวร

## 1. เป้าหมายและวิธีพัฒนา

Prototype คือการ rewrite Configurable Pipeline เพื่อมาแทนระบบเดิมทั้งชุด
Production เป็น reference สำหรับศึกษาและเลือกส่วนที่เหมาะสม ไม่ใช่ข้อผูกมัดว่าต้องใช้
controller, compiler, schema, adapter หรือกฎเดิมทั้งหมด

- Make simple: โค้ดอ่านเข้าใจง่าย มี abstraction เท่าที่จำเป็นต่อ use case จริง
- พัฒนาเป็นรอบเล็กให้ผู้ใช้เรียนรู้และ review ทัน ไม่สร้าง framework ล่วงหน้า
- รักษาหน้าตาและ interaction ของ Form/StepCard ที่ผู้ใช้ปรับไว้
- Technique Draft ยังอยู่กับไฟล์ form ตามโครงที่เลือก ไม่ย้าย models ทั้งหมดไป core โดยอัตโนมัติ
- ใช้รูปแบบ Canvas แบบ STEP 1 → STEP 2 → STEP 3; Arrow หมายถึงลำดับการทำงาน
- Link อยู่ใน Step Configuration; เลือก Step ก่อนหน้าได้ ไม่จำเป็นต้องเป็น Step ที่ติดกัน
- ผลลัพธ์สุดท้ายต้องรักษา payload ของทุก Step และผู้รับต้องถอดได้จริงจากไฟล์ที่ส่งครบ
- เปลี่ยน stego core ได้เมื่อมีหลักฐานว่าจำเป็น แต่ต้องเป็นงานที่ได้รับคำสั่งและมี tests รองรับ
- เป้าหมาย compatibility มาจาก concept ที่ต้องการให้เทคนิคทำงานร่วมกันได้ โค้ด stego ปัจจุบันปรับได้
  หาก writer ทำลาย payload ในพื้นที่ของเทคนิคอื่น ให้ถือเป็นงานแก้ core เพื่อให้ตรง contract
  ไม่ยกข้อบกพร่องนั้นเป็นข้อห้ามถาวรของ pipeline; แต่ยังไม่อ้างว่ารองรับจริงจนแก้และทดสอบผ่าน

## 2. สถานะโค้ดจริงที่ตรวจแล้ว

| ส่วน | สถานะ |
|---|---|
| Pipeline collection | `list[PipelineStepDraft]`; Add, Delete, Clear พร้อม confirmation |
| StepCard/Canvas | Click, hover delete, renumber, Arrow, internal scrolling |
| StepCard geometry | ปัจจุบัน `300 × 160` ใน `step_card.py`; อย่าใช้ค่า 190 จากแชทเก่า |
| Configuration shell | Popup และ Inline, Description, GuideNote |
| Draft persistence | Save/Cancel และเปิดกลับมาแก้ไข เป็น state ในหน่วยความจำ |
| LSB++ | `cover: FileSource | None`; Manual/Linked Picker, persistence, dependency และ single-consumer พร้อม |
| Locomotive | `covers` มี stable output identity; Covers/File Payload รองรับ Manual/Linked พร้อม lifecycle |
| Metadata | `cover: FileSource | None`; Manual/Linked PNG/MP3 Cover และ APIC `image: FileSource` พร้อม persistence, dependency และ lifecycle |
| Step status | SETUP/READY/BLOCKED ทำงานกับ LSB, Locomotive, Metadata Cover และ APIC dependency |
| Linked UI | `LinkedStepToggle` และ `StepOutputPicker` พร้อม preview, unavailable state และ internal scroll |
| Linked data | shared `StepOutput`/`FileSource` ใช้ในทุก Cover/File Payload/APIC role และเข้าร่วม global usage/dependency แล้ว |
| Output catalog | ประกาศ LSB/Metadata output เดียวและ Locomotive multi-output ด้วย stable key แล้ว |
| Prototype execution | Run/Save Outputs ยังไม่เชื่อม execution; ข้อความ Ready ไม่ใช่หลักฐานว่ารันได้ |
| Prototype core | มี scaffold/TODO; การมีชื่อไฟล์ compiler/executor ไม่แปลว่าพัฒนาแล้ว |

ไฟล์หลักสำหรับอ่านและพัฒนา:

- [Pipeline page](gui/pages/sub_pages/embed/configurable_page.py)
- [StepCard](gui/components/step_card.py)
- [Step configuration shell](gui/components/step_config_shell.py)
- [LSB++ form/draft](gui/components/technique_forms/lsb_embed_inputs.py)
- [Locomotive form/draft](gui/components/technique_forms/loco_embed_inputs.py)
- [Metadata host/draft](gui/components/technique_forms/metadata_embed_inputs.py)
- [PNG form/draft](gui/components/technique_forms/metadata/png_form.py)
- [MP3 text + APIC form/drafts](gui/components/technique_forms/metadata/mp3_form.py)
- [Prototype tests](tests/)

`README.md` ยังมีข้อความช่วงแรกว่าไม่มี Step ซึ่งล้าสมัยแล้ว ส่วน `ARCHITECTURE.md`
เป็นแนวคิดเดิมที่ใช้ประกอบการอ่าน ไม่ใช่รายการ architecture ที่อนุมัติทั้งหมดสำหรับงานนี้

### Draft ปัจจุบัน

```python
@dataclass
class PipelineStepDraft:
    key: str
    technique: str
    description: str
    guidenote: str = ""
    technique_inputs: LSBInputsDraft | LocomotiveInputsDraft | MetadataInputsDraft | None = None
```

- LSB ใช้ `cover: FileSource | None`; Locomotive ใช้ `covers: list[LocomotiveCoverDraft]`
  และ `payload_files: list[FileSource]`
- Metadata ใช้ `cover: FileSource | None`; APIC ใช้ `image: FileSource` และเลือก Manual/Previous Output ได้แล้ว
- Add Step เริ่มด้วย `technique_inputs=None`; Save เรียก validate/export แล้วเก็บลง Step
- Key ปัจจุบันใช้ `step_` + UUID4 hex 5 ตัว เช่น `step_3b8f1`
  Renumber ไม่เปลี่ยน key และ Page จำ key ที่เคยใช้เพื่อไม่ให้นำกลับมาใช้ซ้ำหลัง Delete/Clear
- Tests มีเคส Save/Cancel, popup/inline, keys/encryption, summary และ renumber
  รอบจัดทำเอกสารนี้ไม่ได้รัน tests จึงไม่บันทึกยอดผ่านจากแชทเก่าเป็นผลตรวจปัจจุบัน

## 3. ข้อตกลงเรื่องข้อมูล Linked

ใช้ชื่อที่ผู้ใช้เลือก: `StepOutput`, `step_key`, `output_key`
Manual file ใช้ `str` โดยตรง ไม่เพิ่ม `ManualFileSource` wrapper ในรอบนี้

```python
@dataclass(frozen=True, slots=True)
class StepOutput:
    step_key: str
    output_key: str


FileSource = str | StepOutput
```

ข้อมูลสำหรับแสดงใน Picker แยกจาก identity:

```python
@dataclass(frozen=True, slots=True)
class StepOutputInfo:
    reference: StepOutput
    step_number: int
    technique: str
    media_type: str | None
```

Page สร้าง catalog ใหม่จาก `pipeline_steps[:before_step_index]` เมื่อเรียก ไม่เก็บ cache/state ซ้ำ
จึง renumber ค่า `step_number` ได้โดย `StepOutput.step_key` ยังคงเดิม

- `str` หมายถึง manual path เท่านั้น ไม่แอบเก็บ expression ของ Linked เป็น string
- `StepOutput` เป็น reference ไปยัง output หนึ่งไฟล์ ไม่ใช่ bytes/path ของผล Run
- `step_key` อ้าง Step identity ไม่ใช่เลข STEP บน Card หรือ Description
- `output_key` ระบุ output ภายใน Step; ในตัวอย่างใช้ `result`, `output_1`, `output_2`
- ใช้ `None` สำหรับ input เดี่ยวที่ยังไม่เลือก และ list ว่างสำหรับรายการที่ยังไม่มีข้อมูล
- Link อยู่ตรง input ใน Technique Draft ไม่เพิ่ม `cover_links`/`payload_links` ซ้ำใน Page
- `frozen=True` เป็นรายละเอียดที่เสนอเพื่อให้ reference ไม่เปลี่ยนค่าและใช้เป็น dict key ได้

ตัวอย่าง source:

```python
cover = "D:/demo/cover.png"

cover = StepOutput(step_key="step_loco", output_key="output_1")
```

ชื่อ fields ที่เสนอสำหรับการปรับในอนาคต (ยังไม่ใช่โค้ดปัจจุบัน):

| Draft | Source field ที่เสนอ |
|---|---|
| LSBInputsDraft | `cover: FileSource | None` — ทำแล้ว |
| LocomotiveInputsDraft | `covers: list[LocomotiveCoverDraft]`, `payload_files: list[FileSource]` |
| MetadataInputsDraft | `cover: FileSource | None` |
| ApicImageDraft | `image: FileSource` |

Text payload, PNG entries, MP3 frames, APIC picture type/description และ encryption
ใช้โครงเดิมเท่าที่เหมาะสม ไม่เปลี่ยนชื่อ field ที่ไม่เกี่ยวข้องเพียงเพื่อ cleanup

### 3.1 Locomotive stable output identity (L5.0)

Locomotive สร้างหนึ่ง Output ต่อหนึ่ง Cover และ core คืนผลตามลำดับ Cover ที่รับเข้า
จึงห้ามใช้ `output_1`, `output_2` เป็น identity ถาวร เพราะการลบหรือสลับ Cover
จะทำให้ reference เดิมไปชี้คนละไฟล์โดยไม่แจ้งผู้ใช้

แบบที่สรุป:

```python
@dataclass
class LocomotiveCoverDraft:
    source: FileSource
    output_key: str


@dataclass
class LocomotiveInputsDraft:
    covers: list[LocomotiveCoverDraft]
    # payload/encryption fields คงเดิม
```

- `output_key` เป็น internal identity รูปแบบ `output_` + UUID4 hex 8 ตัว
  เช่น `output_a4f91c2e`; ไม่แสดงใน StepCard/Picker โดยตรง
- `StepOutput(step_key, output_key)` ใช้ key นี้เป็น identity; `Output 1`, `Output 2`
  เป็น display label ที่คำนวณจากลำดับ Covers ปัจจุบันเท่านั้น
- การ reorder Covers รักษา `LocomotiveCoverDraft` และ `output_key` เดิม
  แต่คำว่า Output 1/2 ใน UI เปลี่ยนตามลำดับใหม่
- การลบ Cover ทำให้ output identity นั้นหายไป; downstream reference เดิมต้องคงอยู่
  และกลายเป็น BLOCKED จนผู้ใช้เลือก Output ใหม่
- การเปลี่ยน manual file ให้ถือเป็น remove + add: source ใหม่ได้ `output_key` ใหม่
  เพื่อไม่ให้ downstream เปลี่ยนไปใช้คนละ carrier เงียบ ๆ
- เมื่อ files_changed ให้ reconcile ด้วย `source` equality: source เดิมคง key,
  source ใหม่สร้าง key ใหม่ และ source ที่หายถูกนำออก
- Manual source ที่เป็น path เดิมให้ถือเป็น logical source เดิม; รอบนี้ไม่ทำ content hash
  เพื่อตรวจว่าไฟล์ถูกเขียนทับจากภายนอก
- ห้าม Covers ภายใน Step เดียวกันใช้ `output_key` ซ้ำ; imported Draft ที่ key ซ้ำต้องไม่ผ่าน validation
- ตอน Run ให้ zip `covers` กับผลจาก `Locomotive.embed()` ตามลำดับ แล้วเก็บ mapping
  `StepOutput(step_key, cover.output_key) -> output Path`; ไม่อ้าง index หลังจาก mapping แล้ว

ตัวอย่างการ reorder:

```text
ก่อน: carrier_a [output_a4f91c2e] = Output 1
       carrier_b [output_12bd770a] = Output 2

หลัง: carrier_b [output_12bd770a] = Output 1
       carrier_a [output_a4f91c2e] = Output 2

StepOutput("step_loco", "output_a4f91c2e") ยังชี้ carrier_a
```

### 3.2 Metadata linked source contracts (L6.0)

L6 ใช้ `FileSource` เดิมโดยไม่เพิ่ม wrapper, resolver หรือ link fields ชุดใหม่:

```python
@dataclass
class MetadataInputsDraft:
    cover: FileSource | None = None
    payload: MetadataPayloadDraft | None = None


@dataclass
class ApicImageDraft:
    image: FileSource
    picture_type: int = 3
    description: str = ""
```

- L6.1 rename `cover_path` เป็น `cover` โดยตรงแล้วโดยไม่เก็บสอง field เพื่อ compatibility ภายใน
  Prototype; L6.4a จะใช้หลักเดียวกันกับ `image_path` → `image`
- `str` ยังหมายถึง manual filesystem path ส่วน `StepOutput` หมายถึง output ที่จะมีตอน Run;
  Form ห้ามแทน linked source ด้วย preview path หรือ fake workspace path
- Metadata มีหนึ่ง output identity คือ `result`; media ของ output ต้องตรงกับ active payload type
  (`PNGMetadataDraft` → PNG, `MP3MetadataDraft` → MP3)

#### Cover และการเลือก PNG/MP3 form

| Cover source | media ที่ยอมรับ | วิธีเลือก form |
|---|---|---|
| manual `str` | available `.png` หรือ `.mp3` | ตรวจ extension/file ตาม workflow เดิม |
| linked `StepOutput` | catalog media `png` หรือ `mp3` | ใช้ `StepOutputInfo.media_type` เป็นค่าหลัก |
| broken linked reference | ยังไม่ถือว่า valid | ใช้ saved payload type เป็น fallback เพื่อแสดง editor เดิม |

- Metadata Cover มีหนึ่ง source เท่านั้นและเลือก Manual File หรือ Previous Output อย่างใดอย่างหนึ่ง
- Preview path จาก catalog ใช้เพื่อสื่อสารใน GUI เท่านั้น ไม่ใช่ source ที่ Save หรือ Run
- เมื่อ linked source ยัง valid แต่ media ขัดกับ saved payload type ให้รักษา Draft ไว้และแสดง
  dependency/payload mismatch; ห้าม convert payload หรือทิ้งข้อมูลเงียบ ๆ
- เมื่อ reference เสียแต่ payload เป็น PNG/MP3 ให้ยังเปิด form ตาม payload เดิมพร้อม `BLOCKED`;
  ถ้าไม่มี payload type ให้แสดงเฉพาะ source-unavailable state จนผู้ใช้เลือก Cover ใหม่
- เมื่อผู้ใช้ตั้งใจเปลี่ยน Cover ข้าม PNG ↔ MP3 ให้สลับ editor โดยไม่แปลงค่าข้าม format;
  Cancel ไม่แตะ saved Draft และ successful Save จึงแทน payload ด้วยค่าจาก active form

#### MP3 APIC image source

- แต่ละ saved APIC row ต้องมี `image: FileSource`; `picture_type` และ `description` คง contract เดิม
- manual `str` ยังรับ readable `.jpg`, `.jpeg`, `.png` ตาม validation เดิม
- linked `StepOutput` รับเฉพาะ `media_type == "png"` เพราะ outputs ที่ pipeline ประกาศปัจจุบัน
  มี PNG/MP3 และ APIC ต้องเป็นภาพ; MP3 output ห้ามปรากฏใน APIC Picker
- Linked APIC ตรวจ declared media, backward dependency, single-consumer และ upstream chain
  ตอนแก้ Draft/Save; การมี bytes ภาพจริงและการอ่านได้ยังต้องตรวจซ้ำตอน Run
  เพราะ output file ยังไม่เกิด
- APIC Card แสดง Step/Output และ source preview จาก catalog; broken reference ต้องคงทั้ง
  `StepOutput`, picture type และ description พร้อม unavailable state ไม่ลบ row เงียบ ๆ
- APIC ไม่ต้องมี output key ของตัวเอง เพราะ Metadata Step ยังคงสร้าง output เดียว `result`

#### Dependency และ single-consumer

- `step_output_references()` ต้องคืน Metadata Cover ก่อน แล้วตามด้วย linked APIC images ตามลำดับ Draft;
  ทั้ง Cover และ APIC จึงเป็น graph edges และเข้าร่วม backward-only/cycle/recursive validation
- หนึ่ง `StepOutput` ใช้ได้หนึ่งครั้งทั้ง pipeline: ห้ามซ้ำ Cover↔APIC, APIC↔APIC หรือข้าม Step
- Ownership เกิดจาก saved Draft เท่านั้น; การเลือกใน Form ที่ยังไม่ Save ไม่เปลี่ยนสิทธิ์ global
- Reopen ให้ Cover Picker เห็น saved Cover ของตนเอง และ APIC row ที่กำลังแก้เห็น saved source ของ row นั้น;
  Add APIC/role อื่นต้องไม่เห็น output ที่ถูกใช้แล้ว
- Save ต้องตรวจ catalog/dependency/ownership ใหม่เพื่อกัน stale Form; เปลี่ยนเป็น Manual, replace,
  remove, Delete Step หรือ Clear แล้วจึง release ownership ตาม saved lifecycle เดิม
- Producer/output หายหรือ upstream BLOCKED ต้องรักษา reference และทำ Consumer เป็น `BLOCKED`;
  imported duplicate ใช้ first-owner rule เดิมจนผู้ใช้แก้

#### ขอบเขตความรับผิดชอบแบบง่าย

- Page: สร้าง role-specific catalogs/errors, ตรวจ dependency/single-consumer และแสดง StepCard
- `MetadataEmbedInputs`: เก็บ Cover Draft, เลือก source mode/media และ host PNG/MP3 form
- `MP3ApicImagesForm`: เก็บ APIC collection และ source ของแต่ละ row
- ไม่เพิ่ม Metadata controller, source resolver, catalog cache หรือ graph model ใหม่ใน L6

### 3.3 Manual APIC authoring rules

- SIENG2 ใช้กฎหนึ่ง APIC picture type ต่อหนึ่งภาพใน MP3 หนึ่งไฟล์ เพื่อให้ GUI และ config
  ตรงไปตรงมา แม้มาตรฐาน ID3 จะยอมให้บาง type มีหลายภาพเมื่อ description ต่างกัน
- Add form ปิด type ที่ใช้แล้ว; `Change Image` เป็นทางที่ชัดเจนสำหรับแทนรูปโดยรักษา type/description
- Draft จากภายนอกที่มี type ซ้ำยังถูกโหลดไว้ครบ แต่ validation ไม่ผ่านจนผู้ใช้แก้ ห้ามลบหรือทับเงียบ ๆ
- ภาพที่ Add ใหม่ได้ description แบบกระชับจาก picture type โดยอัตโนมัติ แต่ข้อความที่ผู้ใช้แก้เอง
  ต้องไม่ถูกเขียนทับเมื่อเปลี่ยน type
- Description หลัง trim ต้องไม่ซ้ำแบบ case-insensitive และยาวไม่เกิน 64 ตัวอักษร;
  Draft ที่ import มาเป็นค่าว่างยังเก็บได้ แต่ค่าว่างซ้ำไม่ผ่าน validation
- Picture type 1 ต้องเป็นไฟล์ PNG จริงขนาด 32 x 32 pixels; manual APIC อื่นยังรับ JPG/JPEG/PNG
- กฎนี้เป็นฐานของ L6.4; เมื่อ APIC เปลี่ยนเป็น `FileSource` แล้ว linked image ต้องรักษา type/description
  เดิม และข้อที่ต้องใช้ bytes จริงต้องตรวจซ้ำตอน Run

## 4. Workflow หลักที่ผู้ใช้ยกตัวอย่าง

```text
STEP 1 — Locomotive
  Covers: carrier_a.png, carrier_b.png
  Payload: secret.pdf
  Outputs: output_1, output_2

STEP 2 — LSB++
  Cover: StepOutput(step_key="step_loco", output_key="output_1")
  Payload: "123"
  Output: result

STEP 3 — Metadata PNG
  Cover: StepOutput(step_key="step_loco", output_key="output_2")
  Payload: Comment = "456"
  Output: result
```

Step 2 และ Step 3 ต่างอ้าง Step 1; Step 3 ไม่ได้ใช้ Step 2 เป็น Cover
ข้อความ Metadata ต้องอยู่ใน key/value เช่น `{"Comment": "456"}`

ตัวอย่าง Draft ตามแบบที่เสนอ (ไม่ใช่โค้ดที่รันได้กับ classes ปัจจุบัน):

```python
pipeline_steps = [
    PipelineStepDraft(
        key="step_loco",
        technique="locomotive",
        description="Hide PDF across two PNGs",
        technique_inputs=LocomotiveInputsDraft(
            covers=[
                LocomotiveCoverDraft(
                    source="D:/demo/carrier_a.png",
                    output_key="output_a4f91c2e",
                ),
                LocomotiveCoverDraft(
                    source="D:/demo/carrier_b.png",
                    output_key="output_12bd770a",
                ),
            ],
            payload_mode="files",
            payload_files=["D:/demo/secret.pdf"],
            encryption_enabled=False,
        ),
    ),
    PipelineStepDraft(
        key="step_lsb",
        technique="lsbpp",
        description="Embed 123 in output 1",
        technique_inputs=LSBInputsDraft(
            cover=StepOutput(
                step_key="step_loco",
                output_key="output_a4f91c2e",
            ),
            payload_text="123",
            encryption_enabled=False,
        ),
    ),
    PipelineStepDraft(
        key="step_metadata",
        technique="metadata",
        description="Embed 456 in output 2",
        technique_inputs=MetadataInputsDraft(
            cover=StepOutput(
                step_key="step_loco",
                output_key="output_12bd770a",
            ),
            payload=PNGMetadataDraft(entries={"Comment": "456"}),
        ),
    ),
]
```

ผลส่งมอบที่คาดหวังหลังพิสูจน์การรักษา payload แล้ว:

- PNG จาก Step 2 และ PNG จาก Step 3 รวมสองภาพ
- `extract_config.yaml` หนึ่งไฟล์
- ถอด LSB++ ได้ `123`; ถอด Metadata ได้ `456`
- ใช้ภาพปลายทางทั้งสองร่วมกันถอด Locomotive ได้ PDF เดิมครบถ้วน
- ไม่ต้องสร้าง Cover ดั้งเดิมคืนแบบ byte-identical สำหรับ cover stacking
  แต่ต้องพิสูจน์ว่า Locomotive fragments ใน final carriers ยังถอดได้
- ถ้า Locomotive มีสาม Covers แต่เพียงหนึ่ง output ถูกใช้ต่อ ต้องส่ง output ที่เหลือด้วย
  ห้ามเลือก final files จาก Step สุดท้ายเพียงอย่างเดียว

### 4.1 Branching แบบแยก Output และการซ้อนต่อกัน

ระบบใหม่ใช้ **single-consumer rule**: `StepOutput` หนึ่งตัวใช้ได้กับ Consumer สูงสุดหนึ่ง Step
โดยนับรวมทุกบทบาทในอนาคต เช่น Cover, File Payload และ APIC
การแตกกิ่งยังทำได้ด้วยการใช้คนละ Output ของ Producer แบบหลาย Outputs:

```text
A. คนละ output ไปคนละสาย (ตัวอย่างหลัก)
STEP 1 output_1 → STEP 2 LSB++ → result ของ STEP 2
STEP 1 output_2 → STEP 3 Metadata → result ของ STEP 3
Delivery: STEP 2 result + STEP 3 result + extract_config.yaml

B. output เดียวไปหลายสาย (ไม่อนุญาต)
STEP 1 output_1 → STEP 2 LSB++ → result ของ STEP 2
STEP 1 output_1 → STEP 3 Metadata  # Blocked: ใช้โดย STEP 2 แล้ว

C. ซ้อนต่อกันบนสายเดียว (cover stacking)
STEP 1 output_1 → STEP 2 LSB++ → STEP 3 Metadata → result ของ STEP 3
STEP 1 output_2 ไม่ถูกใช้ต่อ
Delivery: STEP 3 result + STEP 1 output_2 + extract_config.yaml
```

ตัวอย่างนี้ถือว่า STEP 1 เป็น Locomotive สอง Covers และแต่ละ Step รักษา payload เดิมได้ตาม contract
กรณี C คือสายต่อเนื่องที่แนะนำ: STEP 2 ใช้ Output ของ STEP 1 และ STEP 3 ใช้ Output ของ STEP 2
ทำให้ผลสุดท้ายรักษา payload ตามลำดับได้ชัดเจนกว่า เมื่อ Consumer ลบ Step หรือเปลี่ยนไปใช้ source อื่น
Output เดิมจะถูก release และ Step อื่นเลือกได้อีกครั้ง

### 4.2 รวม Cover และ Payload จากคนละ Step (Join)

ตัวอย่างที่ผู้ใช้ยืนยันเพิ่มเติม:

```text
STEP 1 — LSB++
  Cover: 1.png
  Payload: "HI"
  Output: step1.png

STEP 2 — Metadata PNG
  Cover: 2.png
  Payload: Comment = "World"
  Output: step2.png

STEP 3 — Locomotive
  Cover: From STEP 2, result
  Payload file: From STEP 1, result
  Output: result.png

Delivery: result.png + extract_config.yaml
```

`result.png` คือพาหะที่ต่อยอดจาก `2.png` ไม่ใช่ไฟล์ manual ต้นฉบับที่ถูกเขียนทับ
ชื่อไฟล์ส่งมอบจะกำหนดภายหลัง; หากตั้งชื่อว่า `2.png` ต้องหมายถึงผลของ STEP 3

- Metadata ของ STEP 2 อยู่ใน PNG carrier ด้านนอก ถอดจาก result.png ได้ `World`
- Locomotive ของ STEP 3 อยู่ใน carrier เดียวกัน ถอดได้ step1.png แบบ byte-identical
- นำ step1.png ที่กู้คืนไปถอด LSB++ ของ STEP 1 ได้ `HI`
- Metadata ของ STEP 2 และ Locomotive ของ STEP 3 ถอดจากไฟล์นอกได้โดยไม่ต้องรอกัน
  ส่วน LSB++ ของ STEP 1 ต้องรอไฟล์จากการถอด STEP 3
- extract config ต้องบอกทั้งเส้นทางใช้ carrier เดียวกันและเส้นทางกู้ไฟล์ payload ชั้นใน
  ผู้รับใช้ไฟล์ส่งมอบและ key ที่ถูกต้องได้โดยไม่พึ่ง workspace หรือ manual files ของผู้ฝัง

### 4.3 หลักเลือก Delivery

เริ่มจาก output ปลายทางที่ไม่มีผู้ใช้ต่อ (leaf outputs) โดยพิจารณาราย output ไม่ใช่ราย Step
รวม output ที่ไม่ถูกใช้ต่อของ Step แบบหลาย Covers ด้วย แล้วตรวจว่าชุดนี้ถอด payload ของทุก Step ได้ครบ

- Cover link: ใช้พาหะปลายทางแทนพาหะก่อนหน้าได้เมื่อรักษาข้อมูลสำหรับ extraction เดิมไว้ครบ
  ไม่จำเป็นต้องย้อนคืนภาพก่อนหน้าแบบ byte-identical
- File Payload/APIC link: ไม่ต้องส่ง intermediate แยกเมื่อกู้ไฟล์นั้นจากผลปลายทางได้ครบทุก byte
- การมี consumer อย่างเดียวไม่พอที่จะตัดไฟล์ออกจาก Delivery ต้องมีเส้นทาง extraction ที่ใช้งานได้
- Single-consumer rule ทำให้ไม่มีสำเนาของ Output เดียวกันหลายสาย; Delivery จึงติดตาม leaf outputs
  และเส้นทาง recovery ได้ตรงไปตรงมากว่า
- ถ้าพิสูจน์การรักษาข้อมูลหรือเส้นทาง recovery ไม่ได้ ต้องรายงานว่า flow ยังไม่รองรับ/ยังไม่ผ่าน
  ห้ามส่งชุดไฟล์ไม่ครบพร้อมอ้างว่าสำเร็จ หรือใช้การส่ง intermediate เพิ่มเพื่อกลบ payload ที่ถูกทำลาย

## 5. สิ่งที่ stego core ให้เรา และ runtime ที่เสนอ

ตรวจจาก `src/core/stego/` และ runtime production ใน workspace นี้:

| Engine | Embed return | การเขียนไฟล์ |
|---|---|---|
| LSBPP | `(png_bytes, suggested_filename)` | ผู้เรียกเขียน bytes |
| Locomotive | `[(suggested_filename, png_bytes), ...]` | ผู้เรียกเขียน bytes; output เรียงตาม Covers |
| Metadata PNG/MP3 | `str` path | Handler เขียนไฟล์เองตาม `save_path` |

- Locomotive มี `last_session_id` ที่ควรเก็บในผล Run เพื่อการถอดหลาย session
- Metadata ต้องได้รับ `save_path` ใหม่ ไม่เช่นนั้นอาจเขียนทับ Cover
- APIC รับ path แล้วอ่าน bytes หรือรับ data bytes ได้; preview ต้องไม่เปลี่ยน bytes ที่นำไปฝัง
- Production มี adapters เขียน output เป็นไฟล์ แล้ว executor resolve reference เป็น path
- `src/core/configurable/config_workspace/` เป็นพื้นที่ของ flow เก่า; typed executor ปัจจุบัน
  ใช้ `<temp>/sieng2/configurable-runs/<run_id>/` เป็นค่าเริ่มต้นและรับ `workspace_base` ได้
- ทั้งหมดนี้เป็นหลักฐานประกอบการออกแบบ ไม่บังคับให้ prototype ใช้ implementation เดิม

แนวทางใหม่ที่เสนอ: Draft เก็บ identity; เมื่อ Run เก็บ mapping แยกต่อ Run:

```python
run_outputs: dict[StepOutput, Path]

# หลัง Step สำเร็จและตรวจไฟล์แล้ว
run_outputs[StepOutput("step_loco", "output_1")] = actual_output_path
```

เมื่อใช้ต่อเป็น Cover/File Payload/APIC ให้ resolve เป็น path ที่ core ต้องการ
Run ใหม่ได้ workspace ใหม่ แต่ reference ใน Draft ยังคงเดิม
ชื่อไฟล์จริงควรไม่ซ้ำแม้อยู่คนละโฟลเดอร์ เพราะ Locomotive multi-file payload
จัด ZIP ตาม basename และปฏิเสธชื่อซ้ำ ข้อสังเกตชุดนี้เป็นข้อมูลตั้งต้นก่อนสรุป L8.0 ด้านล่าง

### 5.1 L8.0 Configurable Pipeline Execution Contract

Contract นี้เป็นแบบของ rewrite ใหม่ Production ใช้เป็นหลักฐานว่า core คืนอะไรและมี pitfall ใด
ไม่ใช้ YAML/string reference หรือ legacy result dict ของ Production เป็นตัวกลางใน Prototype

#### Editor Draft → Qt-independent Run Request

Technique Draft ยังอยู่กับ Form ตามแบบที่ผู้ใช้เลือก ไม่ย้ายทุก Draft ไป core เพื่อให้ได้ runtime
แต่ก่อน Run ต้อง snapshot ค่าที่ Save แล้วเป็น object ชุดใหม่ใน `core/configurable/`:

```python
@dataclass(frozen=True, slots=True)
class EncryptionRequest:
    mode: str | None                 # None, "password", "public_key"
    password: str = field(default="", repr=False)
    public_key_path: str | None = None


@dataclass(frozen=True, slots=True)
class DeclaredOutput:
    reference: StepOutput
    media_type: str                  # "png" หรือ "mp3"


@dataclass(frozen=True, slots=True)
class RunStepRequest:
    step_key: str
    technique: str
    description: str
    guidenote: str
    inputs: object                   # typed LSB/Locomotive/Metadata run inputs


@dataclass(frozen=True, slots=True)
class PipelineRunRequest:
    steps: tuple[RunStepRequest, ...]
```

- Run-input models เป็น Python dataclasses ธรรมดาและใช้ `FileSource`/`StepOutput` ชุดปัจจุบัน
  ห้าม import QWidget, Form หรือ `PipelineStepDraft` จาก core runtime
- Page/controller เป็น boundary ที่รู้จัก Form Draft และแปลงเป็น Run Request; หลังแปลงแล้ว
  compiler/executor/adapters ต้องไม่อ่าน widget หรือ mutable Draft เดิมอีก
- Converter deep-copies collections ให้ Run หนึ่งครั้งเป็น snapshot; ผู้ใช้แก้ editor ระหว่าง Run
  แล้วไม่เปลี่ยน request ที่กำลังทำงาน
- `LSBRunInputs` เก็บ Cover, text และ encryption; `LocomotiveRunInputs` เก็บ Covers พร้อม
  stable `output_key`, file/text payload และ encryption
- `MetadataRunInputs` เก็บ Cover, media type และ payload ที่ normalize แล้ว; APIC ยังเก็บ
  `FileSource` จน executor resolve เป็น path ก่อนส่ง adapter
- Password อยู่ใน memory ของ request เท่านั้น, `repr=False`, ห้าม log/serialize/ใส่ extract config;
  public-key path เป็น input path ไม่ใช่ key bytes
- GUI validation ช่วยผู้ใช้ก่อนกด Run แต่ core compiler ต้อง validate ซ้ำ เพราะ request อาจมาจาก
  import/test/API ในอนาคต

#### Compiled Pipeline และลำดับทำงาน

Compiler รับ `PipelineRunRequest` แล้วคืน immutable plan:

```python
@dataclass(frozen=True, slots=True)
class CompiledStep:
    position: int
    request: RunStepRequest
    dependencies: tuple[str, ...]       # producer step_key ที่ไม่ซ้ำ
    outputs: tuple[DeclaredOutput, ...]


@dataclass(frozen=True, slots=True)
class CompiledPipeline:
    steps: tuple[CompiledStep, ...]
    deliverables: tuple[StepOutput, ...]
```

- Prototype อนุญาต reference ย้อนหลังเท่านั้น จึงใช้ลำดับ Step บน Canvas เป็น execution order
  หลัง compiler ยืนยันว่า dependency ทุกตัวอยู่ก่อนหน้า ไม่ต้องสร้าง topological sorter เพิ่ม
- Compiler รวบรวม `StepOutput` จาก Cover, Locomotive File Payload และ Metadata APIC
  เป็น dependencies; reference ซ้ำในหลาย role ยังผิด single-consumer contract
- LSB++ และ Metadata ประกาศ output เดียวด้วย key `result`
- Locomotive ประกาศหนึ่ง output ต่อ `LocomotiveCoverDraft` โดยใช้ stable `output_key`
  จาก Draft; ลำดับแสดง Output 1/2 ไม่ใช้เป็น runtime identity
- Deliverables คือ declared outputs ที่ไม่มี Step ใด consume ต่อ โดยคำนวณราย output
  ไม่ใช่เลือก output จาก Step สุดท้าย
- Plan ไม่เก็บ absolute workspace path; compiler ตรวจ graph/types/compatibility เท่านั้น

#### StepOutput → Path และ output mapping ต่อ Run

Executor เป็นเจ้าของ mapping ชุดเดียวสำหรับ Run นั้น:

```python
run_outputs: dict[StepOutput, Path] = {}

def resolve_source(source: FileSource) -> Path:
    if isinstance(source, str):
        return Path(source)                 # manual input แบบ read-only
    return run_outputs[source]              # output ที่ Step ก่อนหน้าสร้างสำเร็จแล้ว
```

- Missing key ใน `run_outputs` เป็น execution-contract error ไม่ fallback ไป preview/manual path
- `preview_path` ไม่เข้ามาใน Run Request และไม่มีสิทธิ์ใช้แทน output จริง
- หลัง adapter สร้าง output ครบและ validator ตรวจผ่าน จึง commit mapping ของ Step นั้นพร้อมกัน
  ห้ามลง mapping ทีละไฟล์ระหว่าง Locomotive ยังสร้างผลไม่ครบ
- Suggested filename จาก stego core ใช้เป็นข้อมูลประกอบได้ แต่ไม่ใช้เป็น identity
- Path ภายใน workspace เสนอรูปแบบ
  `steps/<position>_<step_key>/<output_key>.<ext>`; sanitize key และยืนยันว่า path ไม่ออกนอก workspace

Core return → mapping:

| Technique | Core return | Adapter mapping |
|---|---|---|
| LSB++ | `(png_bytes, suggested_name)` | เขียน bytes ที่ declared `result` แล้ว map `StepOutput(step_key, "result")` |
| Locomotive | `[(suggested_name, png_bytes), ...]` | ตรวจจำนวนตรง Covers แล้ว zip ตามลำดับ Cover ไปยัง stable output keys |
| Metadata PNG/MP3 | output path `str` | ส่ง declared staging path เป็น `save_path`, ตรวจไฟล์ แล้ว map `result` |

#### Workspace และ artifact lifecycle

- ทุก Run สร้าง directory ใหม่ด้วย UUID ใต้ temp base เช่น
  `<temp>/sieng2/configurable-runs/<run_id>/`; ห้าม reuse `config_workspace` แบบ shared
- มี marker file และตรวจ resolved parent ก่อน cleanup ตามหลัก safety ของ Production
- Manual Cover/Payload/Key เป็น external read-only inputs; adapter ห้ามเขียนทับ
- ทุก output รวมทั้ง intermediate อยู่ใน workspace ของ Run เท่านั้น
- Adapter เขียนลง staging path/step directory ก่อน; เมื่อ Step สำเร็จครบจึงถือว่า output committed
- Consumed output เป็น intermediate; unconsumed leaf output เป็น final candidate แต่ยังไม่ copy
  ไปปลายทางจน L9 Delivery ทำ package แบบ transactional
- Successful `RunArtifact` เก็บ compiled plan, output mapping, step metadata เช่น
  Locomotive `session_id`, deliverables และ workspace handle
- Workspace ต้องอยู่จนผู้ใช้ Save Outputs สำเร็จหรือยกเลิกผล Run; เมื่อเริ่ม Run ใหม่,
  ปิดหน้า/app หรือ cleanup artifact ให้ลบ workspace ที่ตรวจ marker แล้ว
- Partial files ไม่เป็น deliverables และไม่เปิดปุ่ม Save Outputs

#### Validation, execution errors และ cancellation

Validation/compile เกิดก่อนสร้าง workspace และคืน issue ที่ผูกกับ `step_key`/field:

- Step ไม่มี Draft, key ซ้ำ, technique/input type ไม่ตรง
- manual file/key หาย, payload/encryption ไม่ครบ
- reference หาย, self/forward reference, output key ไม่มี, media ไม่ตรง
- output ถูก consume ซ้ำ, dependency cycle หรือ compatibility ที่ยังไม่รองรับ

ใช้ aggregate `PipelineValidationError(issues)` โดย core ไม่เปิด `QMessageBox` และข้อความห้ามมี
password/key bytes. Execution failure เกิดหลัง workspace ถูกสร้าง ให้ wrap เป็น
`PipelineExecutionError(step_key, cause, artifact)`; artifact เก็บเฉพาะ outputs ของ Step ที่ commit แล้ว
และ partial ของ Step ที่ล้มเหลวไม่เข้าสู่ mapping

Cancellation ระยะแรกใช้ token/event หนึ่งตัว:

- ตรวจ token ก่อนเริ่มแต่ละ Step และใน progress callback ที่ adapter ส่งให้ stego core
- callback ยก `PipelineCancelled` เมื่อถูกขอหยุด; ไม่เริ่ม downstream Step ต่อ
- Cancelled artifact ไม่มี deliverables, Save Outputs disabled และ cleanup workspace ทันที
- Failed artifact ไม่มี deliverables; เก็บ workspace ชั่วคราวเพื่อรายงาน diagnostic ใน session ปัจจุบัน
  แล้ว cleanup เมื่อผู้ใช้ dismiss/เริ่ม Run ใหม่/ปิด app
- ยังไม่ทำ pause/resume, retry จาก Step กลาง, parallel execution หรือ rollback external file
  เพราะ outputs ทั้งหมดอยู่ใน isolated workspace และไม่มีความจำเป็นในรอบแรก

#### Adapter compatibility responsibility

Adapter รับ resolved paths + typed values และ declared staging paths เท่านั้น ไม่รู้จัก GUI:

- **LSB++:** เรียก core แล้วเขียน returned bytes โดยไม่ re-save ซ้ำ; output ต้องเป็น PNG
  และต้องรักษา ancillary chunks กับ bytes หลัง IEND ของ Cover ตาม `merge_reencoded_png`
- **Locomotive:** รับ PNG จริง, append หลัง IEND โดยไม่เปลี่ยน pixel/chunks/trailing เดิม,
  ตรวจจำนวนผลตรง Covers และบันทึก `last_session_id`
- **Metadata-PNG:** ใช้ output path ใหม่, merge text/custom chunks โดยรักษา pixel,
  unrelated chunks และ Locomotive trailing bytes; ห้ามเขียนทับ source
- **Metadata-MP3:** copy source ไป output path ใหม่แล้ว merge ID3 เฉพาะ frame instances ที่กำหนด,
  รักษา audio bytes/frames อื่น; APIC linked source ต้อง resolve เป็นไฟล์ PNG จริงก่อนเรียก core
- ทุก adapter ตรวจ output file มีจริง, media ถูกชนิด และไม่ประกาศ mapping ก่อนผลครบ
- Compiler block flow ที่ทราบว่ายังไม่รับประกัน เช่น LSB++ ซ้ำบน pixel lineage เดียวกัน
  และ Metadata ซ้ำที่สารบัญเดิมอาจถูกทับ จนมี round-trip tests รองรับ
- Pairwise preservation และ main three-step flow ต้องพิสูจน์ด้วย bytes/pixels/chunks/trailing
  และ extraction จริง; การที่ core ไม่ raise error ยังไม่ถือว่า compatible

#### สิ่งที่เลือก reuse/ไม่ reuse จาก Production

Reuse concept: isolated `RunWorkspace`, adapter boundary, structured `RunArtifact`, output mapping
และ leaf-output delivery. ไม่ reuse string `${{...}}`, YAML document เป็น runtime request,
canonical/source ID สองชุด, integer output slots หรือ legacy dict results เพราะ Prototype มี
stable `StepOutput(step_key, output_key)` อยู่แล้ว

#### Pseudocode

```python
request = page.build_run_request()       # snapshot saved Drafts; no widgets in result
compiled = compile_pipeline(request)     # validates before workspace exists
workspace = RunWorkspace.create()
artifact = RunArtifact(compiled, workspace)

try:
    for step in compiled.steps:          # Canvas order; dependencies already validated
        cancel_token.raise_if_cancelled()
        resolved_inputs = resolve_sources(step.request.inputs, artifact.outputs)
        staged_outputs = workspace.staging_paths(step.outputs)

        result = adapter_for(step.request.technique).execute(
            resolved_inputs,
            staged_outputs,
            progress_callback=cancel_token.checked_progress,
        )
        validate_all_declared_outputs(step.outputs, staged_outputs)
        committed = workspace.commit_step_outputs(staged_outputs)
        artifact.outputs.update(committed)  # all outputs of this Step at once
        artifact.step_metadata[step.request.step_key] = result.metadata

    artifact.succeed()
except PipelineCancelled:
    artifact.cancel()
    artifact.cleanup()
except Exception as error:
    artifact.fail(step.request.step_key, error)
    raise PipelineExecutionError(step.request.step_key, error, artifact)
```

#### ตัวอย่าง Pipeline 3 Steps

```text
STEP 1 — Locomotive (step_loco)
  Covers: carrier_a.png [output_a4f91c2e]
          carrier_b.png [output_12bd770a]
  Payload: secret.pdf

STEP 2 — LSB++ (step_lsb)
  Cover: StepOutput("step_loco", "output_a4f91c2e")
  Payload: "123"

STEP 3 — Metadata-PNG (step_meta)
  Cover: StepOutput("step_loco", "output_12bd770a")
  Payload: Comment = "456"
```

Compiled order/dependencies/output declarations:

```text
1. step_loco dependencies=[]
   outputs=[output_a4f91c2e:PNG, output_12bd770a:PNG]
2. step_lsb  dependencies=[step_loco]
   outputs=[result:PNG]
3. step_meta dependencies=[step_loco]
   outputs=[result:PNG]
deliverables=[StepOutput(step_lsb, result), StepOutput(step_meta, result)]
```

Runtime mapping เมื่อจบ:

```text
StepOutput(step_loco, output_a4f91c2e) -> workspace/steps/001_step_loco/output_a4f91c2e.png
StepOutput(step_loco, output_12bd770a) -> workspace/steps/001_step_loco/output_12bd770a.png
StepOutput(step_lsb, result)           -> workspace/steps/002_step_lsb/result.png
StepOutput(step_meta, result)          -> workspace/steps/003_step_meta/result.png
```

สอง output ของ Locomotive เป็น intermediate เพราะถูก consume ต่อ ส่วนสอง `result` เป็น leaf
ที่จะส่งให้ L9 สร้าง package ร่วมกับ `extract_config.yaml`; L8 ยังไม่ publish ไฟล์ออกนอก workspace

## 6. กฎ compatibility ที่ต้องรักษา

ข้อกำหนดด้านล่างเป็นเป้าหมายของระบบใหม่ โค้ดปัจจุบันเป็น implementation ที่แก้ให้ตรงเป้าหมายได้
การตรวจ core ที่บันทึกไว้ก่อนหน้าไม่ใช่การยืนยันว่า round-trip ทุกคู่หรือทุก flow ผ่านแล้ว

แยกการตรวจสองเรื่อง: ชนิดไฟล์ใช้เป็น input ได้หรือไม่ และการเขียนผลรักษา payload เดิมได้หรือไม่
LSB++ ใช้ pixel/channel, Metadata-PNG ใช้ text chunks, Locomotive ใช้ข้อมูลต่อท้าย PNG
การใช้คนละพื้นที่ทำให้ตั้งเป้าหมายการซ้อนร่วมกันได้ แต่ writer ต้องรักษาพื้นที่อื่นด้วย

| การใช้ output เป็น Cover ต่อ | สิ่งที่ core ต้องรักษา |
|---|---|
| Metadata-PNG → Locomotive | PNG chunks และ metadata เดิม; เพิ่ม Locomotive โดยไม่ทำลายข้อมูลเดิม |
| LSB++ → Metadata-PNG | ค่าพิกเซล/บิตที่เก็บ LSB++ แม้ bytes ของ PNG container อาจต่างได้ |
| Locomotive → Metadata-PNG | ข้อมูล Locomotive ต่อท้าย IEND รวมถึง session/fragments ที่ใช้ถอด |
| Metadata-PNG / Locomotive → LSB++ | Metadata chunks และข้อมูลต่อท้าย PNG ขณะเปลี่ยน pixel เพื่อฝัง LSB++ |
| LSB++ → Locomotive | พิกเซลที่ฝัง LSB++ และ metadata เดิมของ carrier |
| Convert/re-save ใน pipeline | รักษาข้อมูลเดิมตาม contract ของสายที่รองรับ; ตรวจ pixel, chunks และ trailing data |

หาก LSB++ ทำข้อมูลท้าย PNG หรือ Metadata หาย ให้แก้การเขียน PNG ของ LSB++;
หาก Locomotive ทำ Metadata หรือพิกเซลที่ฝังไว้เสีย ให้แก้ Locomotive;
หาก Metadata writer ทิ้ง Locomotive trailer หรือเปลี่ยนบิต LSB++ ให้แก้ writer นั้น
แก้ในรอบที่ได้รับคำสั่งพร้อม regression/round-trip tests โดยไม่ขยายงาน GUI/Draft ไปแก้ core ล่วงหน้า
การแก้ core ครอบคลุมกระบวนการที่ระบบควบคุมได้ ไม่รับประกันการแปลงไฟล์ด้วยโปรแกรมภายนอกทุกชนิด

- แยก Cover stacking ออกจากการบรรจุไฟล์เป็น Payload/APIC
- Cover stacking ต้องรักษาข้อมูลที่ใช้ถอด payload เดิม แม้ bytes ทั้งภาพจะเปลี่ยนได้
- File Payload/APIC ต้องคืน bytes ของไฟล์ที่บรรจุให้ครบ ไม่ re-encode ภาพเพื่อใช้ฝัง
- ตรวจประวัติข้อมูลในพาหะชั้นปัจจุบัน ไม่ดูเพียงชื่อเทคนิคของ producer ล่าสุด:
  `LSB++ → Locomotive (Cover) → LSB++ (Cover)` ยังเสี่ยงทับ LSB++ รอบแรก
- ถ้า LSB++ PNG ถูกบรรจุเป็น Payload ของ Locomotive บน Cover ใหม่ ข้อมูล LSB++ อยู่ชั้นใน
  ต้องไม่ถือว่า pixel ของพาหะด้านนอกถูกใช้โดย LSB++ แล้ว
- LSB++ cover รับภาพที่รองรับและ output เป็น PNG; Loco cover รับ PNG
- Metadata cover รับ PNG/MP3; Loco file payload รับไฟล์; APIC รับภาพ
  output ของเทคนิคปัจจุบันมี PNG/MP3 ดังนั้น Linked APIC เลือกได้เฉพาะ PNG
- LSB++ ซ้ำบน pixel ชั้นเดียวกันควร Block จนมีวิธีและผลทดสอบรับประกัน
- Locomotive ซ้ำทำได้ใน concept ถ้า session และ fragments ถูกระบุครบ
- Metadata ซ้ำต้องจัดการ key/frame ชนกันและสารบัญของแต่ละ Step; handler ปัจจุบัน
  ใช้สารบัญการฝังล่าสุด จึงยังรับประกัน extraction หลาย Step ไม่ได้
- Pairwise compatibility ไม่ใช่หลักฐานว่า flow ยาวทั้งชุดถอดได้ ต้องมี round-trip tests

## 7. เรื่องที่ยังต้องตัดสินใจก่อนลงมือส่วนที่เกี่ยวข้อง

1. **Step key สำหรับ Import/Duplicate:** การสร้าง Step ใหม่ใช้ `step_` + UUID4 hex 5 ตัวแล้ว
   พร้อมตรวจชนกับ key ที่เคยใช้ตลอดอายุ Page ส่วน Import/Duplicate ยังต้องเติม key ที่โหลดเข้า
   used-key registry และกำหนดว่าจะปฏิเสธหรือ remap เมื่อ config ภายนอกมี key ซ้ำ
2. **Locomotive output identity:** สรุปแล้วตามข้อ 3.1 ว่า Cover แต่ละรายการเก็บ stable
   `output_key`; เลข Output 1/2 เป็น display order, reorder ไม่เปลี่ยน identity และ
   remove/replace source ทำให้ reference เดิม BLOCKED แทนการ rebind เงียบ ๆ
3. **Output usage:** สรุปใช้ single-consumer rule แล้วตามข้อ 4.1; Output ที่ถูก Save เป็น Cover,
   File Payload หรือ APIC ของ Step หนึ่งแล้วจะไม่ให้ Step อื่นเลือกซ้ำ และจะ release
   เมื่อ Consumer เดิมเลิกใช้หรือถูกลบ
4. **Mixed sources:** Draft แบบ list รองรับ str/StepOutput ผสมได้ แต่ UI รอบแรกจะเปิดให้ผสม
   หรือสลับ Manual/Linked ทั้งกลุ่ม ยังไม่สรุป รวมถึงการจำค่าฝั่งที่ไม่ได้เลือก
5. **Source types location:** สรุปและสร้างใน `core/configurable/step_output.py` แล้ว
   เพื่อให้ Draft, GUI และ runtime ใช้ identity เดียวกันโดย core ไม่ขึ้นกับ PyQt
6. **Save invalid draft/status:** ปัจจุบัน Save ต้องผ่าน form validation
   ต้องตกลงการ Save เมื่อ dependency เสีย โดยรักษา broken reference และข้อความอธิบาย
7. **Imported/manual stego carriers:** ประวัติที่ตามจาก graph ครอบคลุม Step ใน pipeline
   ไม่รับประกันว่าไฟล์ manual ไม่มี payload เดิม ต้องกำหนดวิธีตรวจหรือขอบเขตการรับประกันภายหลัง

แนวทาง status ที่เสนอ: SETUP = ตั้งค่าของตนเองไม่ครบ; BLOCKED = dependency ใช้ไม่ได้;
READY = ผ่านการตรวจ Draft/links ในระดับที่ทำแล้ว ไม่รับประกัน capacity หรือ execution สำเร็จ
เมื่อ Linked file ยังไม่มีจริง ให้แสดง capacity/ขนาดว่าไม่ทราบหรือรอตรวจตอน Run
ห้ามนำค่าจาก manual cover เก่ามาแสดงเป็นค่าของ output ใหม่

## 8. ลำดับพัฒนาที่เสนอ — รอคำสั่งทีละรอบ

- [x] ตรวจ current state และบันทึกข้อตกลงในเอกสารนี้
- [x] K0: เปลี่ยน Stable Step Key เป็น `step_` + UUID4 hex 5 ตัว พร้อม collision retry
- [x] L1a: สร้าง `StepOutput`/`FileSource` และ public export โดยยังไม่เปลี่ยน Technique Draft
- [x] L1b: ปรับ LSB Draft source และจุดใช้งาน manual ที่เกี่ยวข้อง
- [x] L2: สร้างรายการ output ที่จะมีจาก Draft; เริ่ม LSB/Metadata output เดียวและข้อมูลแสดงขั้นต่ำ
- [x] L3: LSB Cover Manual/Linked Picker พร้อม Save/Cancel/reopen, source preview และ summary
- [x] L4: ตรวจ dependencies, source deletion, renumber และ status พร้อมเหตุผล
  - [x] L4.1: lookup Step ด้วย stable key และประกาศข้อมูล output ราย Step
  - [x] L4.2: ตรวจ direct StepOutput dependency พร้อมข้อความสาเหตุ
  - [x] L4.3-L4.4: เชื่อมผลตรวจเข้า StepCard และ unavailable state ใน Picker
  - [x] L4.5-L4.6: lifecycle หลัง Delete/renumber และ recursive dependency propagation
  - [x] L4.7: สร้าง Output usage lookup และ single-consumer validation
  - [x] L4.8: กรอง Picker โดยยังแสดง Output ที่ current Step เป็นเจ้าของ
  - [x] L4.9: ตรวจ Save/BLOCKED, imported duplicate, Delete/Change release และ tests
- [x] L5: สรุป multi-output identity แล้วเชื่อม Locomotive Covers/File Payload
  - [x] L5.0: กำหนด stable output identity ต่อ Cover และ lifecycle ของ reorder/remove/replace
  - [x] L5.1: สร้าง `LocomotiveCoverDraft` และ output-key generator/reconciliation พร้อม unit tests
  - [x] L5.2: migrate manual `cover_paths` เป็น `covers` โดยรักษา GUI/Save/Cancel/summary เดิม
  - [x] L5.3: เพิ่ม Locomotive outputs ใน catalog และแยก stable key จาก display label
  - [x] L5.4: เชื่อม Manual/Previous Output เข้า Locomotive Covers และ persistence
  - [x] L5.5: เชื่อม Previous Output เข้า File Payload และ persistence
  - [x] L5.6: ขยาย single-consumer/dependency/BLOCKED สู่ Locomotive inputs ทั้งหมด
  - [x] L5.7: ตรวจ reorder/remove/replace, Popup/Inline, StepCard และ final verification
- [x] L6: เชื่อม Metadata Cover และ MP3 APIC; เลือก PNG/MP3 form จาก media ของ source
  - [x] L6.0: กำหนด Cover/APIC `FileSource`, media fallback และ single-consumer contracts
  - [x] L6.0a: ปิดกฎ Manual APIC type/description และ Type 1 validation ก่อนเริ่ม Linked APIC
  - [x] L6.1: migrate `MetadataInputsDraft.cover_path` เป็น `cover` โดยรักษา Manual workflow
  - [x] L6.2-L6.3: เชื่อม Cover Picker, media selection, persistence และ StepCard
  - [x] L6.4a: migrate `ApicImageDraft.image_path` เป็น `image` โดยรักษา Manual workflow
  - [x] L6.4b: เชื่อม Previous Output เข้า APIC พร้อม direct media/persistence validation
  - [x] L6.5: ขยาย dependency, single-consumer, cycle และ BLOCKED จาก Cover สู่ linked APIC
  - [x] L6.6: ตรวจ Popup/Inline, StepCard และ final Metadata lifecycle
- [x] L7: ตรวจ GUI/Draft workflow หลักสาม Step ที่ผู้ใช้ยกตัวอย่างให้ครบ
- [ ] L8: เชื่อม execution/workspace/output mapping พร้อม compatibility checks
  - [x] L8.0: กำหนด Execution Contract, Qt boundary, compiled plan, workspace,
    output mapping, lifecycle, error/cancellation และ adapter responsibilities
  - [x] L8.1: สร้าง Qt-independent Run Request models และ Draft → Request converter พร้อม unit tests
  - [x] L8.2: สร้าง compiler สำหรับ dependency/output declarations/deliverables และ validation issues
    - [x] L8.2A: สร้าง immutable Compiler models, validation contracts และ output declarations
    - [x] L8.2B: สร้าง aggregate validation, dependencies, single-consumer และ deliverables
  - [x] L8.3: สร้าง isolated RunWorkspace, resolver และ RunArtifact โดยยังใช้ fake adapters
  - [x] L8.4a: สร้าง LSB++/Locomotive adapters พร้อม stable multi-output mapping
    - [x] L8.4A-LSB: สร้าง real LSB++ adapter พร้อม encryption และ extraction round-trip
    - [x] L8.4B-Locomotive: สร้าง real Locomotive adapter พร้อม stable multi-output mapping
  - [x] L8.4C: สร้าง Metadata-PNG adapter พร้อม preservation tests
  - [x] L8.4D: สร้าง Metadata-MP3 adapter และ resolve linked APIC
  - [ ] L8.5: สร้าง sequential executor, progress, cancellation และ partial-failure lifecycle
  - [ ] L8.6: ทำ pairwise preservation tests; แก้ core เฉพาะ incompatibility ที่พบ
  - [ ] L8.7: เชื่อม Run Pipeline GUI กับ request/compiler/executor โดยไม่ทำ Delivery ล่วงหน้า
  - [ ] L8.8: full round-trip main three-step flow และ final execution verification
- [ ] L9: Delivery/receiver และ full round-trip ของ branching/stacking/join/nested flows ตามข้อ 4

งาน Step key UUID เสร็จแล้วโดยไม่ย้าย model หรือทำ compiler ล่วงหน้า

ตัวอย่างเริ่มแบบ output เดียวที่เสนอ: Metadata-PNG manual → LSB++ Cover
ตัวอย่าง acceptance หลักยังเป็น Locomotive สอง Covers → LSB++/Metadata แยกคนละ output

## 9. การตรวจในแต่ละช่วง

- Source/Draft: manual เดิมยัง Save/Load ได้, reference round-trip, Cancel ไม่เปลี่ยนค่าที่ Save
- Picker: backward-only, media, single/multiple selection และ empty candidates
- Dependency: Delete/renumber, output ลดหรือเปลี่ยนความหมาย, upstream ไม่พร้อม,
  ตรวจความขัดแย้งของเทคนิคที่สะสมหลาย Step ไม่เฉพาะคู่ติดกัน
- GUI: Popup/Inline และ Card แสดง source ตรง Draft; ไม่แสดง READY จาก fake backend state
- Runtime: mapping ใช้ไฟล์ของ Run ปัจจุบัน, จำนวน output ตรงแผน, ไม่เขียนทับ Cover,
  ล้มเหลวแล้วไม่ใช้ partial output เป็นผลสำเร็จ
- Round-trip หลัก: PDF เดิม byte-identical, LSB++ ได้ `123`, PNG Comment ได้ `456`,
  final carriers สองไฟล์ + extract config และกรณีสาม Covers ที่บาง output ไม่ได้ใช้ต่อ
- Nested payload/APIC: ตรวจ bytes ของไฟล์ที่กู้คืน พร้อมถอด payload ภายในต่อได้
- Single-consumer: Output ที่ถูกใช้แล้วไม่ปรากฏให้ Step อื่นเลือก, current owner ยัง reopen ได้,
  Delete/Change แล้ว release และ config ที่ใช้ซ้ำถูก BLOCKED ตามข้อ 4.1
- Join ตามข้อ 4.2: final PNG หนึ่งไฟล์ + extract config; ถอด `World`, กู้ LSB PNG byte-identical,
  แล้วถอด `HI` ได้จากชุดส่งมอบโดยไม่มี workspace เดิม
- Core preservation: ตรวจทั้ง pixel/chunks/trailer ตาม contract ในข้อ 6 และถอด payload เก่า/ใหม่จริง
  หากพบข้อบกพร่องให้เพิ่ม regression test และแก้ core ในรอบที่ได้รับคำสั่ง
- ใช้ `venv` ใน project สำหรับการรัน; ทดสอบตามขอบเขตและกฎ project
- ไม่ render offscreen จนผู้ใช้สั่งประกอบรอบพัฒนา; ไม่เก็บ secrets จริงในเอกสารหรือ test logs
- ไม่ add/commit/push โดยอัตโนมัติ; ไฟล์เอกสารหรือ tests ที่จะขึ้น Git ให้ผู้ใช้กำหนด

## 10. บันทึกรอบล่าสุด

### 2026-09-21 — L8.4D Real Metadata-MP3/APIC execution adapter

- เพิ่ม `execute_metadata_mp3()` ซึ่งรับ typed `MetadataRunInputs`, resolved MP3 Cover `Path`,
  resolved APIC `Path` ตามลำดับ Draft และ staging `result_path`; adapter ไม่อ่าน GUI Draft
  และไม่แยก Manual/Linked APIC หลัง source resolution
- แปลง simple text/URL frames และ complex `COMM`/`USLT`/`USER`/`TXXX`/`WXXX`
  เป็น dictionary contract ของ `MetadataEmbedder`; ตรวจ required fields, frame identity และ duplicate frame ID
- ตรวจ APIC เป็น JPEG/PNG จริง, picture type 0–20 ไม่ซ้ำ, description ยาวไม่เกิน 64 ตัวและไม่ซ้ำแบบ case-insensitive;
  Type 1 ต้องเป็น PNG 32 × 32 ตาม GUI contract
- เขียนผลไปยัง MP3 staging path ใหม่และตรวจ MP3 ซ้ำหลังเขียน; metadata ระบุ output identity `result`,
  frame/APIC count, ordered frame IDs และ size โดยไม่เก็บ source path หรือ image bytes
- Tests ครอบคลุม text-only แบบ simple+complex, manual APIC-only, text+APIC, linked APIC ผ่าน runtime resolver,
  output commit, input preservation, MPEG audio bytes และ unrelated ID3 frame preservation
- Direct Metadata-MP3 adapter tests: `6 passed`; focused core/runtime/adapters: `70 passed`;
  Prototype suite: `353 passed`; full source roots: `603 passed, 3 failed` โดย failures เป็น
  BPP validation เดิมใน `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ adapter
- ไม่พบ failing regression ใน Metadata-MP3 core จึงไม่แก้ production stego core
- รอบนี้ไม่ทำ Executor/Delivery/GUI, ไม่เชื่อม Run button และไม่ stage/commit/push
- งานถัดไป L8.5: สร้าง sequential executor, progress, cancellation และ partial-failure lifecycle

### 2026-09-21 — L8.4C Real Metadata-PNG execution adapter

- เพิ่ม `execute_metadata_png()` ซึ่งรับ typed `MetadataRunInputs`, resolved PNG Cover `Path`
  และ staging `result_path`; payload ต้องเป็น normalized `PNGMetadataRunPayload`
- Adapter ตรวจ entries ไม่ว่าง/ไม่ซ้ำ, Cover และ staging path เป็น PNG, staging path ใหม่ไม่ทับ Cover
  แล้วส่ง path ใหม่นั้นเป็น `save_path` ให้ `MetadataEmbedder`
- หลัง core เขียนเสร็จ ตรวจ returned path, file existence และ PNG container อีกครั้ง;
  metadata ระบุ output identity `result`, ordered keywords, entry count และ size
- Embed/extract round-trip ผ่าน และ integration test ยืนยันว่า adapter ไม่ commit mapping เอง;
  `RunArtifact` commit `StepOutput(step_metadata, result)` หลัง output ผ่านครบเท่านั้น
- Preservation tests ยืนยัน decoded pixels ไม่เปลี่ยน, unrelated private ancillary chunk และ trailing bytes อยู่ครบ,
  LSB++ payload ยัง extract ได้ และ Locomotive session/trailer ยัง extract ได้หลังเขียน Metadata-PNG
- Direct Metadata-PNG adapter tests: `6 passed`; focused core/runtime/adapters: `68 passed`;
  Prototype suite: `347 passed`; full source roots: `597 passed, 3 failed` โดย failures เป็น
  BPP validation เดิมใน `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ adapter
- ไม่พบ failing regression ใน Metadata-PNG core จึงไม่แก้ `src/core/stego/metadata_handlers/png_handler.py`
  หรือ production stego core อื่น
- รอบนี้ไม่ทำ MP3/Executor/Delivery/GUI, ไม่เชื่อม Run button และไม่ stage/commit/push
- งานถัดไป L8.4D: สร้าง Metadata-MP3 adapter สำหรับ text/complex frames และ linked APIC paths

### 2026-09-21 — L8.4B Real Locomotive execution adapter

- เพิ่ม `execute_locomotive()` ซึ่งรับ typed `LocomotiveRunInputs`, resolved Cover/Payload `Path`
  และ staging paths ที่ map ด้วย stable `output_key`; adapter ไม่อ่าน GUI Draft/`StepOutput`
- รองรับ text/file payload และ no encryption/password/public-key; ส่งเฉพาะ active credential ให้ core
  และไม่ใส่ password, key path หรือ key bytes ใน metadata
- ตรวจจำนวน resolved inputs, stable keys, staging paths และผลลัพธ์จาก core ให้ครบก่อนเขียน;
  จับคู่ผลตามลำดับ Cover → stable `output_key` โดย suggested filename เป็น metadata เท่านั้น
- ทุก output ต้องเป็น valid PNG และ staging path ต้องไม่ทับ Cover/Payload/Public Key; หากเขียนกลางชุดล้มเหลว
  adapter ล้าง partial staging files และไม่แตะ `RunArtifact` mapping
- Metadata เก็บ `session_id`, output count, encryption mode และ suggested filename/size ต่อ stable key;
  successful integration test commit ทุก mapping พร้อมกันผ่าน `RunArtifact.commit_step_outputs()`
- Direct Locomotive adapter tests: `6 passed`; focused core/runtime/adapters: `62 passed`;
  Prototype suite: `341 passed`; full source roots: `591 passed, 3 failed` โดย failures เป็น
  BPP validation เดิมใน `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ adapter
- Tests ครอบคลุมหนึ่ง/หลาย Covers, linked Cover, linked file payload, no/password/public-key encryption,
  output-count mismatch, failure กลางชุด, input preservation และ extraction round-trip
- ไม่พบ Locomotive core regression ในขอบเขตที่ทดสอบ จึงไม่แก้ `src/core/stego/locomotive.py`
- รอบนี้ไม่สร้าง Executor/Delivery/GUI, ไม่เชื่อม Run button และไม่ stage/commit/push
- งานถัดไป L8.4C: สร้าง Metadata PNG/MP3 adapter โดย resolve linked APIC เป็น Path ก่อนเรียก core

### 2026-09-21 — L8.4A Real LSB++ execution adapter

- เพิ่ม Qt/GUI-independent `execute_lsbpp()` ซึ่งรับ resolved Cover `Path`, typed `LSBRunInputs`
  และ staging `result_path`; adapter ไม่อ่าน GUI Draft/`StepOutput` และไม่ commit runtime mapping
- รองรับ no encryption, password และ public key โดยส่งเฉพาะ active credential ให้ `LSBPP.embed()`;
  metadata คืนเฉพาะ media type, suggested filename, output size และ encryption mode ไม่มี password/key
- Adapter ปฏิเสธ Cover ที่หาย/ไม่ใช่ PNG, staging path ที่ไม่ใช่ PNG/มีไฟล์อยู่แล้ว และการเขียนทับ Cover;
  ตรวจ returned bytes ด้วย PNG parser ก่อนเขียนและตรวจ staged file ซ้ำหลังเขียน
- ใช้ returned bytes จาก core โดยตรง ไม่เปิด/re-save ภาพ; direct preservation test ยืนยันว่า PNG `tEXt`
  chunk และ bytes หลัง IEND ยังอยู่ครบ พร้อมถอดข้อความ LSB++ ได้จริง
- Direct adapter tests: `7 passed`; focused core/runtime/adapters: `56 passed`;
  Prototype suite: `335 passed`; full source roots: `585 passed, 3 failed` โดย failures เป็น
  BPP validation เดิมใน `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ adapter
- Adapter tests ครอบคลุม no encryption/password/public-key round-trip, Cover read-only,
  staging-before-commit, invalid core output และ PNG metadata/trailing preservation
- ไม่พบ LSB++ core regression ในขอบเขตที่ทดสอบ จึงไม่แก้ `src/core/stego/lsb_pp.py`
- รอบนี้ไม่สร้าง Executor/Delivery/GUI, ไม่เชื่อม Run button และไม่ stage/commit/push
- งานถัดไป L8.4A-Locomotive: รับ resolved Covers/Payload และจับคู่ผลตามลำดับ Cover ไปยัง stable output keys

### 2026-09-21 — L8.3 Isolated runtime foundation

- เพิ่ม Qt-independent `RunWorkspace` ซึ่งสร้าง workspace ใหม่ต่อหนึ่ง run ใต้ temp base ที่กำหนดได้,
  ใช้ unique `run_id`, marker file และโครงสร้าง `steps/<position>_<step_key>/`
- ชื่อ Step/Output ที่นำไปสร้าง path ถูก sanitize แบบ deterministic และทุก path ต้อง resolve อยู่ภายใน
  run root; cleanup ยอมลบเฉพาะ direct child ของ base ที่ marker ตรงกับ `run_id`
- เพิ่ม staging area ต่อ Step และ commit declared outputs แบบ all-or-nothing: ตรวจจำนวน, identity,
  assigned path และไฟล์ครบทั้งหมดก่อน move; หาก move บางรายการล้มเหลวจะ rollback รายการที่ย้ายแล้ว
- เพิ่ม `resolve_source()`: manual `str` resolve เป็น external read-only `Path`; `StepOutput` resolve จาก
  committed mapping ของ run ปัจจุบันเท่านั้น โดยไม่มี fallback ไป `preview_path` หรือ fake path
- เพิ่ม `RunArtifact` สำหรับ compiled plan, committed `StepOutput -> Path`, metadata ราย Step และ state
  `running/succeeded/failed/cancelled`; failed run เก็บ workspace เพื่อวิเคราะห์ ส่วน cancelled cleanup ได้ทันที
- Focused core/request/compiler/runtime tests: `49 passed`; Prototype suite: `328 passed`;
  full source roots: `578 passed, 3 failed` โดย failures เป็น BPP validation เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L8.3
- Runtime tests โดยตรง `11 passed`; ครอบคลุม workspace isolation, path traversal, mapping-only resolver,
  missing output, multi-output commit/rollback, incomplete staging, foreign staging path, states และ safe cleanup
- รอบนี้ยังไม่สร้าง executor/adapters/delivery, ไม่เรียก stego core, ไม่เชื่อม Run button และไม่แก้ production core
- งานถัดไป L8.4a: สร้าง real execution adapter boundary และเริ่มผูก LSB++/Locomotive ตาม stable output mapping

### 2026-09-21 — L8.2B Pipeline compiler

- เพิ่ม `compile_pipeline(PipelineRunRequest)` แบบ Qt-independent; ใช้ลำดับ Canvas เป็นลำดับ
  execution และคืน immutable `CompiledPipeline` เมื่อ validation ผ่านทั้งหมด
- Aggregate structured issues ก่อน raise `PipelineValidationError`: pipeline/step key, technique และ
  input type, required Cover/Payload, manual file/public-key availability, encryption mode,
  Locomotive stable output keys และ Metadata PNG/MP3/APIC required values
- รวบรวม `StepOutput` จาก LSB Cover, Locomotive Covers/File Payload และ Metadata Cover/APIC;
  ตรวจ missing/self/forward/output reference, media ของแต่ละ input role และ global single-consumer
- Dependencies เก็บ producer step keys แบบไม่ซ้ำตามลำดับที่พบ; Locomotive หลาย outputs จาก producer
  เดียวกันจึงสร้าง dependency เพียงรายการเดียว
- Deliverables คำนวณราย declared output ตามลำดับ Step/output โดยเลือกเฉพาะ leaf ที่ไม่มี consumer;
  main acceptance flow จึงได้ LSB `result` และ Metadata `result` โดย Locomotive outputs เป็น intermediate
- Compiler ตรวจ public-key path ว่ามีไฟล์ แต่ยังไม่ parse/validate cryptographic key, ไม่ตรวจ capacity
  และยังไม่อ้างว่า pixel/chunk/trailer preservation ผ่าน; งาน compatibility เชิง stego อยู่ L8.6
- Error messages ไม่บันทึก password หรือ key bytes; focused test ตรวจว่า dormant password ไม่ปรากฏ
  ใน exception text/repr
- Focused core/request/compiler tests: `38 passed`; Prototype suite: `317 passed`;
  full source roots: `567 passed, 3 failed` โดย failures เป็น BPP validation เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L8.2B
- รอบนี้ไม่สร้าง workspace/resolver/executor/adapters/delivery, ไม่เรียก stego core, ไม่แก้ GUI/
  production core และไม่ stage/commit/push
- งานถัดไป L8.3: สร้าง isolated `RunWorkspace`, `FileSource` resolver และ `RunArtifact`
  โดยเริ่มพิสูจน์ lifecycle ด้วย fake files/adapters ก่อนเรียกเทคนิคจริง

### 2026-09-21 — L8.2A Immutable Compiler contracts

- แทนที่ Prototype compiler scaffold ด้วย Qt-independent contracts ได้แก่ `DeclaredOutput`,
  `ValidationIssue`, `PipelineValidationError`, `CompiledStep` และ `CompiledPipeline`
- Models ใช้ frozen dataclasses และ tuple collections; structured issue เก็บ `code`, `message`,
  `step_key` และ `field` โดย exception สรุปจำนวน issues โดยไม่พิมพ์ input/secret values
- เพิ่ม `declare_step_outputs()` สำหรับ output identity/media เท่านั้น: LSB++ ประกาศ `result/png`,
  Metadata ประกาศ `result/png|mp3` จาก saved media type และ Locomotive ประกาศ PNG ตาม stable
  `output_key` ของ Covers โดยรักษาลำดับเดิมและไม่ deduplicate key เงียบ ๆ
- Incomplete/unsupported request คืน declaration ว่างในรอบนี้เพื่อให้ L8.2B เป็นผู้สร้าง
  aggregate validation issues; ยังไม่มี `compile_pipeline()` หรือการตรวจ filesystem/dependency
- Public exports ผ่าน `core.configurable`; fresh-process test ยืนยันว่า compiler contracts ไม่โหลด PyQt6
- Focused core/request/compiler tests: `27 passed`; Prototype suite: `306 passed`;
  full source roots: `556 passed, 3 failed` โดย failures เป็น BPP validation เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L8.2A
- รอบนี้ไม่สร้าง workspace/resolver/executor/delivery, ไม่เรียก stego core, ไม่แก้ GUI/production core
  และไม่ stage/commit/push
- งานถัดไป L8.2B: สร้าง `compile_pipeline()` ให้ aggregate validation, ตรวจ references/media/
  single-consumer, สร้าง ordered dependencies และ leaf deliverables

### 2026-09-20 — L8.1 Qt-independent Run Request boundary

- เพิ่ม immutable Run Request models ใน `core/configurable/run_request.py` โดยไม่มี PyQt/Form import;
  ใช้ frozen dataclasses, tuple collections และ `FileSource`/`StepOutput` identity ชุดเดิม
- ครอบคลุม `EncryptionRequest`, LSB++, Locomotive Covers/stable output keys, PNG entries,
  MP3 simple/complex frames, APIC manual/linked sources, Metadata host, Step และ Pipeline request
- Password ใช้ `repr=False`; converter เก็บเฉพาะ encryption mode ที่ active และไม่พก dormant
  password/public-key path เข้า request โดยไม่จำเป็น
- เพิ่ม `run_request_converter.py` เป็น GUI boundary ที่รู้จัก Technique Draft แต่คืนเฉพาะ core
  request; core models ไม่ import GUI และ compiler/executor รอบถัดไปไม่ต้องอ่าน Form Draft
- เพิ่ม `build_pipeline_run_request()` และ `EmbedConfigurablePage.build_run_request()` ซึ่ง snapshot
  เฉพาะค่าที่ Save แล้วใน `pipeline_steps`; ไม่อ่าน widget/active shell และไม่เชื่อม Run button
- Collections จาก mutable Draft ถูกแปลงเป็น tuple และ nested MP3/APIC/Locomotive values ถูกสร้างใหม่;
  การแก้ Draft หลังสร้าง request จึงไม่เปลี่ยน request ที่กำลังใช้
- Step ที่ยังไม่มี `technique_inputs` ถูก snapshot ด้วย `inputs=None` เพื่อให้ L8.2 compiler
  รวบรวม validation issue; unsupported technique หรือ Draft type ที่ไม่ตรงถูกหยุดที่ boundary
- Focused core/request tests: `16 passed`; Prototype suite: `295 passed`; full source roots:
  `545 passed, 3 failed` โดย failures เป็น BPP validation เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L8.1; fresh core import
  ยืนยันว่า `config_prototype.core.configurable.run_request` ไม่โหลด PyQt6
- รอบนี้ไม่สร้าง compiler/workspace/executor/delivery, ไม่เรียก stego core, ไม่เชื่อม Run button,
  ไม่แก้ production core และไม่ stage/commit/push
- งานถัดไป L8.2: สร้าง immutable compiled plan และ aggregate validation issues จาก
  `PipelineRunRequest` โดยยังไม่สร้าง workspace หรือเรียก technique adapters

### 2026-09-18 — L8.0 Configurable Pipeline Execution Contract

- ตรวจ Prototype Draft/Linked graph, stego core ทั้ง LSB++, Locomotive, Metadata PNG/MP3
  และ Production compiler/adapters/executor/delivery โดยใช้ Production เป็น reference เท่านั้น
- สรุป boundary ให้ Page/controller snapshot GUI Draft เป็น typed Qt-independent Run Request;
  compiler/executor/adapters ห้ามอ่าน widget หรือ mutable Form Draft ระหว่าง Run
- กำหนด CompiledStep ตาม Canvas order หลัง validate backward dependencies, stable output declarations
  และ leaf deliverables ราย `StepOutput`; รอบแรกไม่เพิ่ม topological sorter/parallel execution
- กำหนด per-run `dict[StepOutput, Path]`, isolated UUID workspace, atomic per-step mapping,
  intermediate/final lifecycle และห้ามใช้ preview/fake path เป็น runtime source
- กำหนด validation/compile errors แยกจาก execution errors พร้อม cancellation token และกฎ
  partial failure โดยไม่มี pause/resume/retry/rollback ที่ยังไม่จำเป็น
- กำหนด preservation responsibility ของ LSB++, Locomotive, Metadata-PNG/MP3 adapters
  และต้องพิสูจน์ด้วย extraction/byte-level round-trip ไม่ใช้เพียงผลว่า core ไม่ raise
- บันทึก pseudocode และ main three-step flow: Locomotive สอง outputs แตกไป LSB++/Metadata;
  output ของสอง consumer เป็น deliverables ส่วน Locomotive outputs เป็น intermediates
- รอบนี้แก้เฉพาะเอกสาร contract; ไม่ implement runtime, ไม่แก้ GUI/stego core และไม่ run tests
- งานถัดไป L8.1: สร้าง Run Request models กับ Draft → Request boundary converter พร้อม unit tests

### 2026-09-17 — L6.6 Final Metadata lifecycle และ L7 GUI/Draft acceptance

- ตรวจ Metadata PNG manual/linked Cover, MP3 text-only, APIC-only, Text+APIC และ APIC
  manual/linked ผ่าน Popup/Inline tests เดิมร่วมกับ acceptance tests ใหม่
- ยืนยัน Save/Cancel/Reopen, StepCard summary/status, broken reference, single-consumer,
  recursive BLOCKED, Delete Producer/Consumer และ Clear โดย Draft/reference ไม่หายเงียบ ๆ
- เพิ่ม acceptance flow จริงในระดับ GUI/Draft: Locomotive สอง Covers/Outputs → LSB++ ใช้
  Output 1 → Metadata-PNG ใช้ Output 2; ทั้งสาม Card เป็น READY และ Picker แยก ownership ถูกต้อง
- Popup Metadata และ Inline LSB++ Save ค่าเดิมได้; การแก้แล้ว Cancel ไม่เปลี่ยน saved Draft
  และ stable `step_key`/`output_key`
- ลบ Producer แล้ว LSB++/Metadata branches ทั้งคู่คง `StepOutput` เดิมและเป็น BLOCKED;
  ลบ Consumer แล้ว ownership ของ output ถูก release และ Clear คืน canvas เป็น empty state
- พบ Output Catalog geometry regression เมื่อ selected preview อยู่ก่อน output แถวถัดไป:
  scroll content สูงถูกต้อง แต่ parent stacks บีบ picker จนแถวท้ายซ้อนกับ Metadata form
- แก้ที่ shared `StepOutputPicker` ให้แจ้ง minimum height ที่เปลี่ยนตาม rows/preview และให้
  LSB++, Locomotive, Metadata Cover/APIC source stacks รับความสูงนั้น; Metadata host ส่งต่อ
  ความสูงผ่าน cover stack จึงใช้ outer page scroll แทนการซ้อน widget
- เพิ่ม geometry regression test ยืนยันว่า output ทุกแถวจบก่อน Metadata content form
  โดยไม่ย้าย preview หรือเปลี่ยน Output Catalog contract
- Focused Metadata/StepCard/acceptance matrix: `165 passed`; Prototype suite: `283 passed`
- Full source test roots: `516 passed, 3 failed`; failures เดิมเป็น BPP validation ใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L6.6/L7
- Offscreen สำคัญไม่มี glyph สี่เหลี่ยม:
  `tmp/offscreen/l6_6_l7_acceptance/01_main_three_step_ready.png`,
  `02_metadata_linked_inline.png`, `03_deleted_producer_blocked.png`
- ไม่แก้ production core, ไม่ stage/commit/push
- งานถัดไป L8: กำหนด execution/workspace/output mapping และเริ่มพิสูจน์ compatibility
  ของ flow หลักด้วยผลไฟล์จริง โดยแยกออกจาก GUI/Draft ที่ปิด acceptance แล้ว

### 2026-09-17 — L6.5 APIC dependency graph และ single-consumer

- เพิ่ม linked APIC ทุก row เข้า `step_output_references()` หลัง Metadata Cover ทำให้ APIC
  เป็น graph edge จริงสำหรับ usage lookup, backward-only, cycle และ recursive propagation
- Page ส่ง APIC catalog ที่กรองตาม media `png`, dependency chain, ownership และ saved role;
  output ที่ Cover/File Payload/APIC ตำแหน่งอื่นใช้แล้วไม่เสนอให้ Add APIC ใหม่
- Save รวบรวม Metadata Cover และ APIC refs เพื่อตรวจ output ซ้ำภายใน Step ก่อน แล้วตรวจ
  global dependency/ownership ใหม่ ป้องกัน stale form ที่เปิดค้างไว้ก่อน output ถูกจอง
- เมื่อ stale Save ล้มเหลว ฟอร์มเดิมคง `StepOutput` ไว้ พร้อมเปลี่ยน APIC Card/Picker เป็น
  unavailable state และแสดงเหตุผล ไม่สร้าง path ปลอมหรือลบ row
- Producer/output หายหรือ upstream BLOCKED ยังคง stable `step_key`/`output_key`; StepCard
  consumer และ downstream chain เปลี่ยนเป็น `BLOCKED` โดย renumber ไม่แก้ identity
- เพิ่ม self-reference error ที่ชัดเจนก่อน cycle guard; imported multi-step cycle ยังคงใช้
  `Circular dependency detected.` ตามเดิม
- Focused linked/dependency/APIC tests: `78 passed`; Prototype suite: `279 passed`
- Full source test roots: `512 passed, 3 failed`; failures เดิมเป็น BPP validation ใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L6.5
- Offscreen ตรวจ available, consumed และ broken APIC แล้ว ไม่มี glyph สี่เหลี่ยม:
  `tmp/offscreen/l6_5_apic_dependency/01_available_apic.png`,
  `02_consumed_apic.png`, `03_broken_apic.png`
- ไม่แก้ execution, production core/QSS และไม่ได้ stage/commit/push
- งานถัดไป L6.6: ตรวจ Popup/Inline, StepCard, release ownership หลัง Change/Remove/Manual
  และ final Metadata lifecycle ก่อนปิด L6

### 2026-09-17 — L6.4b APIC Previous Output workflow

- เพิ่ม `LinkedStepToggle` และ `StepOutputPicker` ใน `MP3ApicImagesForm`; Picker รับเฉพาะ
  catalog media `png` และไม่เสนอ MP3 output เป็น APIC source
- Add/Change/Remove, load/export และ Manual workflow ใช้ `ApicImageDraft.image: FileSource` เดียวกัน;
  Change reuse add form เป็น edit state โดยไม่เพิ่ม draft/state ชุดซ้ำ
- Picker แสดง Step, technique, output label, source filename และ preview จาก `preview_path`;
  saved linked Card แสดงข้อมูลชุดเดียวกันโดยไม่ใช้ preview path เป็น source จริง
- Broken `StepOutput` ถูกเก็บและ export กลับครบ; เมื่อแก้ Card Picker แสดง unavailable reason
  และ Save ถูก direct validation block โดยไม่สร้าง fake path
- Page ส่ง APIC catalog/error แยกจาก Metadata Cover, ตรวจ backward producer/media PNG ซ้ำตอน
  Save และ StepCard summary อ่าน linked APIC ได้; รอบนี้ตั้งใจยังไม่เรียก global usage,
  recursive dependency, cycle หรือ BLOCKED สำหรับ APIC
- เพิ่ม focused tests สำหรับ PNG filtering, preview/presentation, linked Add/Change/Remove,
  broken round-trip และ Inline Save/Reopen/Cancel
- Focused APIC/Metadata/Page tests: `114 passed`; Prototype suite: `272 passed`
- Full source test roots: `505 passed, 3 failed`; failures เดิมเป็น BPP validation ใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L6.4b
- Offscreen ตรวจ Manual card, linked Picker และ saved linked Card แล้ว ไม่มี glyph สี่เหลี่ยม:
  `tmp/offscreen/l6_4b_apic/manual_apic.png`, `linked_apic_picker.png`,
  `linked_apic_saved.png`
- ไม่แก้ execution, production core หรือ QSS และไม่ได้ stage/commit/push
- งานถัดไป L6.5: ให้ linked APIC เข้าร่วม `step_output_references()`, global
  single-consumer, recursive dependency/cycle, stale Save และ StepCard `BLOCKED`

### 2026-09-17 — L6.4a APIC FileSource Draft migration

- เปลี่ยน `ApicImageDraft.image_path: str` เป็น `image: FileSource` โดยตรงและไม่เก็บ
  compatibility field ซ้ำ; Manual APIC ยังคงเก็บ path เป็น `str`
- ปรับ Add/Change/Remove, deep-copy load/export, Card preview/filename/size, validation และ
  StepCard summary ให้ใช้ field ใหม่ โดย Manual workflow และข้อความเดิมยังทำงาน
- `StepOutput` ผ่าน structural validation และ load/export ได้โดยไม่ถูกแปลงเป็น preview/fake path;
  Card ใช้ safe placeholder และ validation แจ้งว่ายังรอ Previous Output editor ใน L6.4b
- เพิ่ม focused tests สำหรับ field contract, manual/linked source และ lossless linked round-trip;
  เปลี่ยน test fixtures ทั้งหมดจาก `image_path=`/`.image_path` เป็น `image=`/`.image`
- Focused APIC/Metadata/Page tests: `107 passed`; Prototype suite: `268 passed`
- Full test roots (`tests`, `config_prototype/tests`, `prototype/image/tests`): `501 passed,
  3 failed`; failures เดิมเป็น BPP validation ใน `prototype/image/tests/test_lsb_replacement.py`
  และไม่เกี่ยวกับ L6.4a; การรันจาก workspace root โดยไม่ระบุ roots ถูก local `tmp/pytest-*`
  ขัดขวางด้วย Windows permission ระหว่าง collection
- ไม่เพิ่ม Previous Output toggle/picker, APIC dependency, single-consumer, QSS, offscreen
  หรือ production-core change และไม่ได้ stage/commit/push
- งานถัดไป L6.4b: เชื่อม Previous Output เข้า APIC พร้อม catalog media, persistence และ
  direct validation โดยใช้ `image: FileSource` ที่เตรียมไว้

### 2026-09-09 — Output Catalog vertical alignment regression fix

- พบต้นเหตุจากรอบ internal scrolling วันที่ 2026-09-07: `QScrollArea` ถูกกำหนดความสูงตาม
  content/สูงสุด 300px แต่ `StepOutputPicker` ยังขยายเต็มพื้นที่ และ `QVBoxLayout` ไม่มี stretch
  จึงกระจายพื้นที่ว่างก่อน Header, ระหว่าง Header/list และท้าย list
- เพิ่ม bottom stretch หนึ่งจุดใน reusable `StepOutputPicker`; Header/list จึงยึดด้านบน
  ขณะที่พื้นที่ส่วนเกินอยู่ท้าย layout และ scroll/preview behavior เดิมไม่เปลี่ยน
- เพิ่ม geometry regression assertion ว่า Header เริ่มที่ `y=0` และ list อยู่ต่อจาก Header ทันที
- Offscreen ตรวจ LSB++, Locomotive และ Metadata แบบหนึ่ง output: Header `y=0`, list `y=27`,
  row สูง 34px, scrollbar maximum 0; Locomotive 16 outputs สูง 300px และ maximum 304
- โหลด Segoe UI/Arial/Courier New เฉพาะ render process ทำให้ภาพไม่มี glyph สี่เหลี่ยม;
  ไม่เปลี่ยน runtime font หรือ QSS
- Focused linked tests: 23 passed; `config_prototype/tests`: 266 passed
- Full workspace: 671 passed, 3 failed; เป็น BPP failures เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ Output Catalog
- งานถัดไปยังเป็น L6.4a migrate `ApicImageDraft.image_path` → `image: FileSource`

### 2026-09-09 — L6.2-L6.3 Metadata Cover Previous Output workflow

- เชื่อม `LinkedStepToggle` และ `StepOutputPicker` เข้ากับ Metadata Cover โดยรับเฉพาะ
  catalog media `png`/`mp3`; Draft ยังเก็บ `StepOutput` โดยตรงและไม่สร้าง fake path
- เลือก PNG/MP3 form จาก `StepOutputInfo.media_type`; broken saved reference ใช้ชนิด
  `PNGMetadataDraft`/`MP3MetadataDraft` ที่บันทึกไว้เพื่อเปิด editor เดิม โดย Picker แสดงสาเหตุ unavailable
- Page สร้าง catalog ตาม backward-only, dependency และ single-consumer rules; current owner
  ยังเห็น source ของตนเอง และตรวจ dependency ซ้ำตอน Save เพื่อกัน stale form
- Metadata Cover เข้าร่วม `step_output_references()`, cycle/recursive dependency และ StepCard
  `BLOCKED`; Delete producer ไม่ลบ reference และ Card summary รองรับ linked PNG/MP3
- ตรวจ Save/Cancel/Reopen ทั้ง Popup/Inline, PNG/MP3 form selection, summary, broken reference
  และ ownership ด้วย focused tests ใหม่
- Focused Metadata tests: 30 passed; linked/page regression set: 105 passed;
  `config_prototype/tests`: 266 passed
- Full workspace: 671 passed, 3 failed; เป็น BPP failures เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L6.2-L6.3
- รอบนี้ไม่แก้ APIC source, stego/core execution, production Configurable Pipeline หรือ QSS
  และไม่ทำ offscreen render
- งานถัดไป: L6.4a migrate `ApicImageDraft.image_path` → `image: FileSource` โดยรักษา
  Manual APIC workflow ก่อนเชื่อม Picker ใน L6.4b

### 2026-09-09 — L6.1 Metadata Cover FileSource migration

- เปลี่ยน `MetadataInputsDraft.cover_path` เป็น `cover: FileSource | None` โดยตรงและไม่เก็บ
  compatibility field/state ซ้ำ; manual path ยังเป็น `str` ตาม shared contract
- ปรับ Metadata host ให้ Manual PNG/MP3 select/change/clear, media detection, FileInfoBar,
  payload load/export และ validation ทำงานกับ `cover` โดยหน้าตาเดิมไม่เปลี่ยน
- `StepOutput` สามารถ load/export ผ่าน form ได้โดยไม่สูญหาย; รอบนี้ยังไม่มี Previous Output UI
  และ validation จะแจ้งว่า linked target ยังใช้ไม่ได้แทนการส่ง reference เข้า `Path()`
- ปรับ Page preview/media/StepCard consumers ให้ manual cover ใช้ field ใหม่และมี type guard;
  Popup/Inline และ summary/status เดิมยังผ่าน regression tests
- เพิ่ม focused tests ล็อก field contract, manual/linked source และ lossless linked round-trip;
  เปลี่ยน fixtures เดิมทั้งหมดจาก `cover_path=` เป็น `cover=`
- Focused Metadata/Page/dependency tests: `115 passed`; Prototype suite: `261 passed`
- Full workspace: `666 passed, 3 failed`; failures เดิมเป็น BPP validation ใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ L6.1
- ไม่มี APIC Draft/UI, QSS, stego core หรือ execution change และไม่ render offscreen ตามคำสั่ง
- งานถัดไป L6.2-L6.3: เชื่อม Manual/Previous Output Picker เข้ากับ Metadata Cover,
  เลือก PNG/MP3 form จาก catalog media และต่อ persistence/StepCard โดยใช้ Draft นี้

### 2026-09-09 — Manual APIC type and description rules

- เพิ่ม default description แบบกระชับครบ APIC type 0-20; Add form เริ่มที่ `Front cover`
  และเปลี่ยน default ตาม picture type โดยไม่เขียนทับ description ที่ผู้ใช้พิมพ์เอง
- กำหนดหนึ่งภาพต่อหนึ่ง picture type; type ที่ใช้แล้วถูก disable ใน ComboBox ขณะที่ Draft
  จากภายนอกที่มี type ซ้ำยังถูกเก็บครบและถูก validation block แทนการลบข้อมูล
- Description ตรวจหลัง trim แบบ case-insensitive และจำกัด 64 ตัวอักษรทั้งใน QLineEdit/validation
- เพิ่ม validation ของ Type 1 ให้เป็นไฟล์ PNG จริงขนาด 32 x 32 pixels; Change Image เดิมยังรักษา
  picture type และ description
- Focused Metadata/APIC tests: `105 passed`; Prototype suite: `259 passed`
- Full workspace: `664 passed, 3 failed`; failures เดิมเป็น BPP validation ใน
  `prototype/image/tests/test_lsb_replacement.py` และไม่เกี่ยวกับ APIC
- ไม่แก้ QSS, stego core, Pipeline page หรือ Linked Output implementation และไม่ render offscreen
  ตามข้อตกลงให้รอผู้ใช้สั่ง
- งานถัดไปยังเป็น L6.1: migrate Metadata Cover `cover_path` → `cover: FileSource | None`
  โดยรักษา Manual PNG/MP3 workflow ก่อนเพิ่ม Picker

### 2026-09-09 — L6.0 Metadata linked source contracts

- ตรวจ current Metadata host, PNG/MP3 payload drafts, APIC collection และ Page แล้วพบว่า
  `cover_path`/`image_path`, FileInfoBar, QPixmap และ path validation ยังผูกกับ manual path โดยตรง
- สรุปให้ Metadata Cover ใช้ `cover: FileSource | None` และ APIC ใช้ `image: FileSource`;
  ไม่เก็บ field เก่าและใหม่ซ้ำ ไม่สร้าง wrapper หรือ fake output path
- Linked Cover ใช้ catalog media เลือก PNG/MP3 form; broken reference ใช้ saved payload type
  เป็น fallback เพื่อรักษา editor/data เดิมพร้อม BLOCKED แทนการทิ้ง Draft
- Manual APIC ยังรับ JPG/JPEG/PNG แต่ linked APIC รับ PNG output เท่านั้น; actual output bytes
  ตรวจตอน Run เพราะ editor มีเพียง declared media และ preview source
- กำหนดให้ Cover/APIC ทุก occurrence เข้าร่วม backward dependency, cycle และ single-consumer;
  current owner reopen ได้, Add/role อื่นไม่เห็น output ที่ใช้แล้ว และ Save ตรวจ stale form ซ้ำ
- แบ่งหน้าที่ตามโครงเดิม: Page ดู catalog/dependency, Metadata host ดู Cover/media,
  MP3 APIC form ดู collection; ไม่เพิ่ม controller/resolver/graph model ใน L6
- รอบนี้แก้เฉพาะเอกสาร contract ไม่มี GUI/implementation/test/offscreen change
- งานถัดไป L6.1: rename `MetadataInputsDraft.cover_path` → `cover`, ปรับ manual path consumers
  และ tests โดยยังไม่เพิ่ม Linked Picker หรือเปลี่ยน APIC

### 2026-09-07 — Output Catalog internal scrolling before L6

- เปลี่ยน `StepOutputPicker` ให้ Header อยู่นอก viewport และให้รายการ Output กับ preview
  เลื่อนภายใน `QScrollArea` ของ Picker เอง
- รายการสั้นปรับความสูงตาม content โดยไม่แสดง scrollbar; รายการยาวหยุดที่ `300px`
  และแต่ละ Output row มีความสูงขั้นต่ำ `34px` จึงไม่ถูก layout บีบจนข้อความถูกตัด
- ใช้ global scrollbar style เดิม และเพิ่ม selector แบบเจาะจงให้ viewport โปร่งใส;
  ไม่เปลี่ยนสี ตัวอักษร หรือ interaction ของ Picker
- เพิ่ม geometry test ครอบคลุมรายการสั้น/ยาว, scrollbar maximum และ row height
- Offscreen ตรวจทั้ง Popup และ Inline: Popup `height=300`, `maximum=367`; Inline
  `height=300`, `maximum=152`; rows ที่วัดได้สูง `34px` เท่ากัน
- โหลด Segoe UI/Courier New ให้ offscreen script โดยตรงเพื่อแก้ glyph สี่เหลี่ยมเฉพาะการตรวจภาพ;
  ไม่เปลี่ยน runtime font ของ application
- ผลตรวจ: linked/StepCard focused `80 passed`, Prototype suite `253 passed`;
  full suite `658 passed, 3 failed` โดย failures เป็น BPP validation เดิมนอกงานนี้
- งานถัดไปยังเป็น L6 โดยเริ่ม L6.0 กำหนด Metadata Cover/APIC source และ media contracts

### 2026-09-07 — L5.7 Final Locomotive linked-output lifecycle

- เพิ่ม focused lifecycle tests ยืนยันว่า Linked Covers/File Payload ที่ Save ผ่าน Popup
  เปิดต่อใน Inline ได้ตรง Draft เดิม และ Cancel ไม่แก้ saved Draft หรือ stable output key
- ยืนยันการ reorder Covers ว่า source เดิมรักษา `output_key`; StepCard/tooltip ของ Consumer
  คำนวณ Output 1/2 ใหม่จากลำดับปัจจุบันโดย reference ภายในยังชี้ output เดิม
- ยืนยันว่า remove/replace Cover ไม่ลบ downstream reference เงียบ ๆ แต่ทำให้ Consumer เป็น
  `BLOCKED` และ Picker แสดง saved output เป็น unavailable พร้อมเหตุผล
- ยืนยันการเปลี่ยน File Payload จาก Previous Output เป็น Manual แล้ว Save ว่าปลด
  single-consumer ownership; Step ถัดไปจึงเลือก output เดิมได้อีกครั้ง
- ไม่พบ defect ใหม่ใน implementation ระหว่าง final verification จึงไม่มี GUI/QSS change และ
  ไม่เพิ่ม abstraction นอกขอบเขต; รอบนี้เปลี่ยนเฉพาะ focused tests และเอกสารสถานะ
- ผลตรวจ: L5 focused `14 passed`, Locomotive/StepCard regression `86 passed`, Prototype suite
  `252 passed`; full suite `657 passed, 3 failed` โดย failures ยังเป็น BPP validation เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` ซึ่งอยู่นอก L5
- ไม่ render offscreen ตามข้อตกลงที่ให้รอผู้ใช้สั่ง
- L5 ปิดครบแล้ว; งานถัดไปคือ L6 เชื่อม Metadata Cover และ MP3 APIC กับ Previous Output
  โดยเริ่มจากกำหนด role/media compatibility และ Draft migration ที่เล็กที่สุดก่อน

### 2026-09-07 — L5.5-L5.6 Linked File Payload and Locomotive dependencies

- เปลี่ยน `LocomotiveInputsDraft.payload_paths` เป็น `payload_files: list[FileSource]`;
  manual file workflow เดิมยัง derive paths จาก source โดยไม่มี state ซ้ำ
- เพิ่ม Manual File/Previous Output และ multi-output Picker ใน File Input tab;
  linked payload Save/Cancel/reopen ได้และ StepCard ระบุว่าขนาดจริงตรวจตอน Run
- ขยาย saved-reference lookup ให้รวม Locomotive Covers และ active File Payload ทำให้
  single-consumer ครอบคลุมข้าม Step และข้าม input role
- Output ที่ current Step ใช้อยู่แสดงเฉพาะ Picker ของ role เดิม; Step อื่นมองไม่เห็นจน
  Consumer เปลี่ยน source หรือถูกลบ และ Save ตรวจ stale form ซ้ำอีกชั้น
- ปฏิเสธ Output เดียวที่ถูกเลือกซ้ำภายใน Locomotive Step เดียว แม้อยู่คนละ Cover/Payload role
- ขยาย direct/recursive dependency, cycle detection และ StepCard BLOCKED ไปยัง linked Covers
  และ File Payload; broken reference ไม่ถูกลบและแสดง unavailable state ใน multi Picker
- เพิ่ม L5.5-L5.6 focused tests รวมเป็น `11 passed`; prototype suite `249 passed`
- Full suite ได้ `654 passed, 3 failed`; failures ยังเป็น BPP validation เดิมสามรายการใน
  `prototype/image/tests/test_lsb_replacement.py` ซึ่งอยู่นอก L5.5-L5.6
- ไม่มี QSS change และไม่ได้ render offscreen ตามคำสั่งที่ให้รอผู้ใช้ร้องขอ
- งานถัดไป: L5.7 ตรวจ Popup/Inline, reorder/remove/replace, switching mode,
  release ownership, StepCard/Picker และ lifecycle ทั้งหมดก่อนปิด Stage L5

### 2026-09-07 — L5.3-L5.4 Locomotive multi-output catalog and linked covers

- เพิ่ม optional `display_name` ใน `StepOutputInfo`; Locomotive ใช้ stable UUID output key
  เป็น identity แต่ Picker/summary แสดง Output 1/2 จากลำดับ Covers ปัจจุบัน
- `build_output_catalog()` ประกาศหนึ่ง PNG output ต่อหนึ่ง Locomotive Cover และ preview
  ย้อนกลับไปยัง source ของ output แต่ละตัว ไม่ใช้ preview เดียวแทนทุก output
- ขยาย `StepOutputPicker` ด้วยโหมด multiple โดยไม่เปลี่ยน single-selection API ของ LSB++;
  ผู้ใช้เลือก/ยกเลิกหลาย Previous Outputs และลำดับการเลือกกลายเป็นลำดับ Covers
- Locomotive Cover Card ใช้ toggle Manual File/Previous Output และเก็บ linked sources
  เป็น `LocomotiveCoverDraft`; Save/Cancel/reopen รักษาทั้ง source และ output identity
- Save ตรวจ direct availability/media/usage ของ linked covers ด้วย validator เดิม และ StepCard
  แสดง linked summary/tooltip โดยไม่เผย UUID แก่ผู้ใช้
- รอบนี้ยังไม่เพิ่ม Previous Output ให้ File Payload และยังไม่ขยาย recursive dependency,
  single-consumer ownership และ BLOCKED lifecycle ของ Locomotive ซึ่งเป็น L5.5-L5.6
- เพิ่ม focused tests 4 รายการ; focused integration `106 passed` และ prototype suite `242 passed`
- Full suite ได้ `647 passed, 3 failed`; failures ยังเป็นสาม BPP validation cases เดิมใน
  `prototype/image/tests/test_lsb_replacement.py` ซึ่งอยู่นอก L5.3-L5.4
- ไม่มี QSS change และไม่ได้ render offscreen ตามคำสั่งที่ให้รอจนผู้ใช้ร้องขอ
- งานถัดไป: L5.5 เชื่อม Previous Output เข้า File Payload พร้อม persistence จากนั้น L5.6
  ขยาย reference lookup, single-consumer, recursive dependency และ BLOCKED ให้ครบทั้งสอง role

### 2026-09-07 — L5.2 Manual Locomotive covers migration

- เปลี่ยน `LocomotiveInputsDraft.cover_paths` เป็น
  `covers: list[LocomotiveCoverDraft]`; ไม่มี compatibility field ซ้ำสองชุด
- Form เก็บ `locomotive_covers` เป็น state หลักและ derive manual paths สำหรับ
  `MultiFileDropWidget`, validation และ summary เดิม
- การเลือก/reorder/replace ไฟล์เรียก `link_sources_to_covers()` จึงรักษา output key
  เฉพาะ source เดิม และสร้าง identity ใหม่ให้ source ใหม่
- Load/export ทำสำเนา cover entries พร้อมรักษา output key ทำให้ Save/Cancel/reopen
  ทั้ง Popup และ Inline ไม่เปลี่ยน identity
- ปรับ StepCard summary/tooltip ให้ใช้ manual paths จาก `cover.source`; รูปแบบข้อความเดิมไม่เปลี่ยน
- ผลตรวจ focused form `12 passed`, StepCard/shell `60 passed` และ prototype suite `238 passed`
- Full suite ได้ `643 passed, 3 failed`; เป็น BPP validation failures เดิมทั้งสามรายการใน
  `prototype/image/tests/test_lsb_replacement.py` ซึ่งอยู่นอก L5.2
- ไม่มี QSS/layout change และไม่ได้ render offscreen ตามขอบเขต L5.2
- งานถัดไป: L5.3 ประกาศ Locomotive multi-output ใน Output Catalog โดยใช้ stable
  `output_key` แต่คำนวณ Output 1/2 จากลำดับ Covers ปัจจุบัน

### 2026-09-07 — L5.1 Locomotive cover identity primitives

- เพิ่ม `LocomotiveCoverDraft(source, output_key)` โดย `source` รองรับทั้ง manual path และ
  `StepOutput` แต่ยังไม่ migrate `LocomotiveInputsDraft.cover_paths` หรือเชื่อม GUI ในรอบนี้
- เพิ่ม generator รูปแบบ `output_` + UUID4 hex 8 ตัว พร้อม retry เมื่อชน key ที่ใช้อยู่
- เพิ่ม reconciliation ที่จับคู่ด้วย source equality: reorder รักษา key, remove ตัด entry เดิม
  และ source ใหม่/replace ได้ key ใหม่ โดยรองรับ linked source ตั้งแต่ระดับ model
- export API ผ่าน `technique_forms` package และเพิ่ม focused tests; ผลตรวจ `11 passed`
- Full suite ได้ `642 passed, 3 failed`; failures ทั้งสามอยู่ใน
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP validation ซึ่งอยู่นอก L5.1
  และไม่ได้แก้ในรอบนี้
- ไม่มี GUI/QSS change และไม่ได้ render offscreen ตามขอบเขต L5.1
- งานถัดไป: L5.2 migrate manual `cover_paths` เป็น `covers` โดยรักษา Form,
  Save/Cancel/reopen, summary และ validation เดิม

### 2026-09-07 — L5.0 Locomotive stable output identity design

- ตรวจยืนยันว่า `Locomotive.embed()` คืนผลหนึ่งรายการต่อ Cover ตามลำดับที่รับเข้า
  และ Draft ปัจจุบันเก็บเพียง `cover_paths: list[str]` จึงยังไม่มี stable identity
- สรุปให้หนึ่ง `LocomotiveCoverDraft` เก็บ `source` และ internal `output_key`
  รูปแบบ `output_` + UUID4 hex 8 ตัว; UI ยังแสดง Output 1/2 ตามลำดับปัจจุบัน
- Reorder รักษา key เดิม; remove/replace ทำให้ key เดิมหายและ downstream BLOCKED
  เพื่อป้องกัน silent rebind
- กำหนด runtime mapping ให้ zip Cover entries กับผล core เพียงครั้งเดียว แล้วอ้างด้วย
  `StepOutput(step_key, output_key)` แทน index
- รอบนี้แก้เฉพาะเอกสารออกแบบ; ไม่ได้เปลี่ยน Python/QSS หรือ render offscreen
- งานถัดไป: L5.1 สร้าง model/generator/reconciliation รอบเล็กใน
  `loco_embed_inputs.py` พร้อม focused tests ก่อน migrate Form

### 2026-09-07 — L4.7-L4.9 Single-consumer rule

- `StepOutput` หนึ่งตัวมี Consumer ได้สูงสุดหนึ่ง Step; ปัจจุบัน lookup รวบรวม LSB linked cover
  และมีจุดขยายเดียวสำหรับ Locomotive Cover/File Payload และ Metadata Cover/APIC ในรอบถัดไป
- Picker กรอง Output ที่มี Step อื่นใช้แล้ว แต่ current owner ยังเห็นและ reopen ค่าที่ Save ไว้ได้
- Save ตรวจ usage ซ้ำอีกครั้ง จึงป้องกัน form ที่เปิดค้างไว้แล้ว Output ถูก Step อื่นจองภายหลัง
- Imported/manual Draft ที่อ้าง Output เดียวกันซ้ำ ให้ Consumer แรกตามลำดับเป็น owner
  และ Consumer ภายหลังเป็น BLOCKED พร้อมระบุ Step ที่กำลังใช้อยู่
- Delete Consumer หรือเปลี่ยนกลับไปใช้ Manual source จะ release Output เดิมโดยอัตโนมัติ
- เปลี่ยนข้อตกลงจาก same-output fan-out เป็น single-consumer; ยังแตกกิ่งได้ด้วยคนละ Output
  ของ Producer แบบ multi-output
- Focused linked-output tests: 30 passed; `config_prototype/tests`: 233 passed
- Full workspace: 638 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- Offscreen: `tmp/offscreen/l4_single_consumer/step3_only_unused_step2.png` และ
  `tmp/offscreen/l4_single_consumer/step1_released_after_consumer_delete.png`
- งานถัดไป: L5 กำหนด stable Locomotive multi-output identity ก่อนขยาย usage lookup
  ไปยัง Covers และ File Payload

### 2026-09-06 — L4.5-L4.6 Delete/renumber และ recursive propagation

- แยก direct validation กับ full dependency validation ให้ Card, Picker และ Save
  ใช้กฎ recursive เดียวกันโดยไม่ทำลาย contract ของ `linked_output_error()` เดิม
- เมื่อ Producer ถูกลบ broken `StepOutput` ยังคงอยู่ใน Draft; Step ถัดไปและ consumer
  ที่ลึกกว่าจะเป็น BLOCKED ตามลำดับ โดยไม่ลบลิงก์เงียบๆ
- การลบ Step ที่อยู่ก่อน Producer จะเปลี่ยนเฉพาะเลขแสดงผล; stable key,
  reference, Card status, summary และ Arrow ถูก rebuild จาก collection เดิม
- เพิ่ม cycle guard สำหรับ imported/manual Draft graph ที่ผิดปกติ ให้แสดง
  `Circular dependency detected.` แทนการ recurse ไม่จบ
- Focused dependency tests: 20 passed; `config_prototype/tests`: 228 passed
- Full workspace: 633 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- รอบนี้ไม่ได้ render offscreen เพราะไม่ได้รับคำสั่งในรอบนี้
- งานถัดไป: L5 กำหนด stable multi-output identity ของ Locomotive ก่อนเชื่อม
  Previous Output เข้า Covers และ File Payload

### 2026-09-06 — L4.3-L4.4 StepCard BLOCKED และ Picker unavailable state

- เพิ่ม `step_dependency_error()` แล้วให้ `render_step_cards()` override Card เป็น `BLOCKED`
  เมื่อ LSB linked cover ใช้ไม่ได้ โดย Tooltip ของ status แสดงเหตุผลจาก validator
- เมื่อลบ Producer จะคง `StepOutput` เดิมใน Draft, summary แสดง `Source unavailable`
  และไม่เปิดเผย stable key ในข้อความสำหรับผู้ใช้
- เพิ่ม unavailable state ใน `StepOutputPicker` แสดงเหตุผลพร้อมคำแนะนำให้เลือก Previous Output ใหม่
  โดยยังแสดง Output อื่นที่ใช้แทนได้ และไม่แสดง preview ของ reference ที่เสีย
- LSB form ได้รับเฉพาะ catalog entries ที่ configured และผ่าน PNG compatibility;
  saved broken reference ยังคงถูกโหลดในโหมด Previous Output แยกจาก candidates
- Save ที่ยังใช้ broken reference ถูกปฏิเสธโดย Page ก่อนเปลี่ยน Pipeline Draft;
  เมื่อเลือก Output ใหม่จึง Save ได้ และ Cancel ยังคง Draft เดิม
- เพิ่ม focused tests สำหรับ upstream SETUP, Producer deletion, incompatible media, unavailable Picker,
  rejected/replacement Save และ Cancel persistence
- Focused dependency tests: 15 passed; `config_prototype/tests`: 223 passed
- Full workspace หลังแก้โค้ด: 627 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- รอบนี้ไม่ได้ render offscreen เพราะผู้ใช้ไม่ได้สั่ง และไม่ได้แก้ recursive propagation
- งานถัดไป: L4.5-L4.6 ตรวจ Delete/renumber lifecycle เพิ่มเติมและ propagate BLOCKED ผ่าน dependency หลายชั้น

### 2026-09-06 — L4.1-L4.2 Direct dependency lookup/validation

- เพิ่ม `step_index_for_key()` และปรับ `step_draft_for_key()` ให้ lookup จาก stable key จุดเดียว
  จึงยังหา Producer เดิมได้เมื่อเลข Step เปลี่ยนจาก Delete/renumber
- เพิ่ม `step_output_info(step_index, output_key)` เป็นจุดประกาศ output ของ Step เดี่ยว
  และให้ `build_output_catalog()` reuse จุดนี้แทนการสร้างข้อมูลซ้ำ
- เพิ่ม `linked_output_error(reference, consumer_index, accepted_media)` ซึ่งคืน `None` เมื่อ direct link ใช้ได้
  หรือคืนเหตุผลสำหรับ source หาย, self/future reference, output key ไม่มี, Producer ยังไม่ตั้งค่า,
  media ไม่ทราบชนิด และ media ไม่เข้ากัน
- รอบนี้ยังไม่เปลี่ยน StepCard status, Picker unavailable UI, Save validation หรือ recursive propagation
- Focused dependency tests ใหม่: 9 passed; `config_prototype/tests`: 217 passed
- Full workspace: 622 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- ไม่ได้ render offscreen เพราะรอบนี้เป็น logic-only และผู้ใช้ไม่ได้สั่งภาพ
- งานถัดไป: L4.3-L4.4 เชื่อมผลตรวจเข้า StepCard BLOCKED และแสดง saved reference ที่ใช้ไม่ได้ใน Picker

### 2026-09-06 — L3 LSB Manual/Linked Picker และ source preview

- สร้าง `LinkedStepToggle` และ typed `StepOutputPicker` ใน Prototype โดย selection ใช้
  `StepOutput(step_key, output_key)` ไม่ผูกกับเลข Step ที่เปลี่ยนเมื่อ renumber
- เชื่อม Manual File/Previous Output เข้ากับ LSB Cover Card ผ่าน `QStackedWidget`
  โดย Manual workflow เดิมยังคงใช้ FileDropWidget และคำนวณ capacity ตามเดิม
- LSB Picker รับเฉพาะ previous output ที่ catalog ระบุเป็น PNG; MP3 และ media ที่ยังไม่ทราบชนิดไม่ถูกเสนอ
- เพิ่ม `preview_path` เป็น display metadata ใน `StepOutputInfo`; ไม่เพิ่ม path ลง `StepOutput`
  และไม่สร้าง output/temp ปลอมก่อน Run
- Preview ใช้ Cover ต้นทางของ producer และไล่ย้อนผ่าน LSB linked cover ได้ แสดง filename พร้อมข้อความชัดเจนว่า
  actual output จะถูกสร้างตอน Run; ถ้าอ่านภาพไม่ได้จะแสดง unavailable state
- Header STEP/TECHNIQUE/OUTPUT จัดกึ่งกลาง และ tooltip แสดง filename/Step number โดยไม่เปิดเผย stable key แก่ผู้ใช้
- Save/Cancel/reopen ผ่านทั้ง Popup และ Inline; StepCard แสดง `From STEP N, Output N`
  ส่วน linked capacity ระบุว่ารอตรวจตอน Run
- Focused Prototype suite: 208 passed
- Full workspace: 613 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- Offscreen ตรวจ standalone Picker, Popup, Inline และ StepCard summary แล้ว; โหลด Segoe UI/Courier New
  โดยตรงสำหรับ Qt offscreen เพื่อไม่ให้ฟอนต์เป็นสี่เหลี่ยม
- งานถัดไป: L4 ตรวจ reference ที่หาย, producer ยังไม่พร้อม, Delete/renumber และแสดง BLOCKED พร้อมเหตุผล

### 2026-09-06 — L2 Single-output catalog

- เพิ่ม `StepOutputInfo(reference, step_number, technique, media_type)` แยกข้อมูลแสดงจาก identity
- เพิ่ม `build_output_catalog(before_step_index)` ซึ่งคำนวณ previous outputs ใหม่ทุกครั้งโดยไม่เก็บ cache
- LSB ประกาศ `result` เป็น PNG; Metadata ประกาศ `result` และระบุ PNG/MP3 เมื่อ Draft บอก media ได้
- Metadata ที่ยังไม่ตั้งค่าอยู่ใน catalog ด้วย `media_type=None` เพื่อไม่สร้าง type ที่เดาเอง
- Locomotive ยังไม่รวม เพราะจำนวนและ identity ของ multi-output ต้องสรุปใน L5
- ตรวจ first-step empty, previous-only/order, Metadata media และ renumber โดย reference เดิมไม่เปลี่ยน
- Focused catalog/source tests: 7 passed; `config_prototype/tests`: 203 passed
- Full workspace: 608 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- รอบนี้ไม่มี Picker, dependency status, Technique Form/QSS change หรือ offscreen
- งานถัดไป: L3a สร้าง UI สำหรับเลือก Manual/Linked source โดยใช้ catalog นี้ ก่อนเชื่อมเข้า LSB Form

### 2026-09-06 — LSB FileSource Draft migration

- เปลี่ยน `LSBInputsDraft.cover_path` เป็น `cover: FileSource | None`
- Form เก็บค่าจริงใน `cover_source`; คง `cover_file_path` เป็น property สำหรับ Manual UI เดิม
- Manual source ยังตรวจไฟล์และคำนวณ capacity ตามเดิม; `StepOutput` เก็บ/validate ระดับ form/export ได้
  โดยยังไม่ resolve path หรือคำนวณ capacity ก่อน execution
- StepCard ป้องกันการส่ง `StepOutput` เข้า `Path()` และแสดง `Linked output` พร้อม identity ใน tooltip ชั่วคราว
- เพิ่ม tests สำหรับ linked load/export และ StepCard rendering พร้อมปรับ manual assertions เป็น `draft.cover`
- LSB-focused tests: 11 passed; `config_prototype/tests`: 199 passed
- Full workspace: 604 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- รอบนี้ไม่มี Picker, output catalog, dependency validation, QSS change หรือ offscreen
- งานถัดไป: L2 สร้าง output catalog ขั้นต่ำสำหรับ single-output Steps ก่อนทำ LSB Manual/Linked Picker

### 2026-09-06 — Shared StepOutput/FileSource

- สร้าง `core/configurable/step_output.py` ตามชื่อที่ผู้ใช้เลือก และนำ scaffold `references.py` ออก
- เพิ่ม immutable `StepOutput(step_key, output_key)` และ `FileSource = str | StepOutput`
- Public export ผ่าน `config_prototype.core.configurable`
- เพิ่ม focused tests สำหรับ equality/hash mapping, immutability และ manual/linked source contract
- `config_prototype/tests/test_core_models.py`: 3 passed
- `config_prototype/tests`: 197 passed
- Full workspace ไม่ได้รันซ้ำ; ผลล่าสุดก่อนรอบนี้คือ 599 passed, 3 failures นอก Configurable Prototype
- รอบนี้ไม่มีการแก้ Technique Forms, GUI/QSS หรือทำ offscreen
- งานถัดไป: L1b ปรับ LSB cover Draft ให้เก็บ `FileSource` โดยรักษา manual workflow เดิม

### 2026-09-06 — Stable Step Key

- เปลี่ยน key จากตัวนับ `prototype_step_N` เป็น `step_` + UUID4 hex 5 ตัว
- Page เก็บ `used_step_keys` และสุ่มใหม่เมื่อชน รวม key ที่ถูก Delete/Clear แล้ว
- ปรับ tests ให้ตรวจรูปแบบ/ความไม่ซ้ำ/ความคงที่ และจำลอง collision retry แบบ deterministic
- `config_prototype/tests/test_gui_step_card.py`: 55 passed
- `config_prototype/tests`: 194 passed
- Full workspace: 599 passed, 3 failed; failures เดิมอยู่นอกขอบเขตที่
  `prototype/image/tests/test_lsb_replacement.py` เรื่อง BPP ไม่ยก ValueError ตาม test
- รอบนี้ไม่มี GUI/QSS change และไม่ได้ render offscreen
- งานถัดไป: สร้าง `StepOutput`/`FileSource` เป็น shared source types รอบเล็กก่อนย้าย LSB Draft

### 2026-09-06 — ยืนยัน stacking, fan-out, join, Delivery และเป้าหมาย core preservation

- อัปเดต concept จากคำยืนยันของผู้ใช้: core ปรับได้เพื่อรักษา payload ของเทคนิคอื่น
  ข้อบกพร่องของ implementation ปัจจุบันไม่ใช่ข้อจำกัดถาวรของแบบใหม่
- เพิ่มตัวอย่างแยกคนละ output, same-output fan-out และ stacking พร้อมชุด Delivery
- เพิ่ม Join: LSB++ `HI` เป็น file payload และ Metadata `World` เป็น Cover ของ Locomotive
- ขยายกฎ leaf outputs ด้วยเงื่อนไขว่าต้องถอดทุก payload ได้ครบ พร้อมแนวทาง receiver สำหรับ fan-out
- สถานะยังเป็นการออกแบบ; รอบนี้แก้เฉพาะเอกสารนี้ ไม่ตรวจ core ซ้ำหรือรัน GUI/algorithm tests
- งานถัดไปยังเป็น review แผนและสั่งรอบ Step key หรือ L1; ไม่ได้เริ่ม execution/core implementation

### 2026-09-06 — จัดทำแผนร่วมกัน

- อ่าน Page, technique Draft APIs, Linked TODO files, core scaffold และ execution-bar wiring
- อ่าน `config_desgin.txt` และบันทึกความต้องการ UUID แบบสั้นเป็นงานที่ยังต้องสรุปรายละเอียด
- พบ README ส่วนสถานะล้าสมัย; บันทึกข้อเท็จจริงที่ตรวจได้ไว้ในข้อ 2
- เพิ่มเอกสารนี้และ `config_prototype/AGENTS.md` สำหรับชี้ให้แชทถัดไปอ่าน
- รอบนี้ไม่มีการแก้ Python/QSS และไม่ได้รัน GUI/algorithm tests
- งานถัดไป: ผู้ใช้ review/แก้แผน แล้วสั่งรอบ Step key หรือ L1 ตามขอบเขตที่เลือก
