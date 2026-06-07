import streamlit as st
import fitz          # PyMuPDF
import pandas as pd
import io
import re
from typing import Optional

# ============================================================
# Page Configuration
# ============================================================
st.set_page_config(
    page_title="Hansard Curator",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# Light Theme + Contrast Accents
# ============================================================
st.markdown(
    """
<style>
:root {
  --bg:        #f8fafc;
  --surface:   #ffffff;
  --surface-2: #f1f5f9;
  --border:    #e2e8f0;
  --text:      #0f172a;
  --text-mute: #64748b;
  --accent:    #4f46e5;   /* indigo */
  --accent-2:  #ec4899;   /* pink */
  --accent-3:  #0ea5e9;   /* sky */
  --good:      #059669;
}

.stApp           { background-color: var(--bg); color: var(--text); }
.main            { background-color: var(--bg); }
section[data-testid="stSidebar"] { background-color: var(--surface) !important;
                                   border-right: 1px solid var(--border); }

h1, h2, h3, h4, h5, h6, p, span, label, div { color: var(--text); }
.stMarkdown p, .stCaption, [data-testid="stCaptionContainer"] { color: var(--text-mute); }

h1 { text-align: center; margin-bottom: 0.25rem; font-weight: 700; }
h1 span { background: linear-gradient(135deg, var(--accent), var(--accent-2));
          -webkit-background-clip: text; -webkit-text-fill-color: transparent; }

.stAlert { background-color: var(--surface) !important;
           border: 1px solid var(--border) !important;
           color: var(--text) !important;
           border-left: 4px solid var(--accent) !important; }

.stButton>button {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #ffffff;
    border: none;
    border-radius: 10px;
    font-weight: 600;
    padding: 0.55rem 1.2rem;
    transition: transform .15s ease, box-shadow .15s ease;
}
.stButton>button:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 18px -6px rgba(79, 70, 229, .55);
}
.stDownloadButton>button {
    background: var(--surface);
    color: var(--accent);
    border: 1.5px solid var(--accent);
    border-radius: 10px;
    font-weight: 600;
}
.stDownloadButton>button:hover {
    background: var(--accent);
    color: #ffffff;
}

[data-testid="stMetricValue"] { color: var(--accent) !important; font-weight: 700; }
[data-testid="stMetricLabel"] { color: var(--text-mute) !important; }

[data-testid="stFileUploader"] { border-radius: 12px; }
[data-testid="stTextInput"] input { border-radius: 8px; border: 1.5px solid var(--border); }
[data-testid="stTextInput"] input:focus { border-color: var(--accent); }

div[data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 10px; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# MP LOOKUP  (loaded from uploaded Excel)
# ============================================================

_STRIP_TITLES = [
    'YAB ', 'YB ',
    # Senator prefixes — must come before plain DATUK SERI etc.
    "SENATOR DATO' SERI DIRAJA DR. ", "SENATOR DATO' SERI DIRAJA ",
    "SENATOR DATO\u2019 SERI DIRAJA DR. ", "SENATOR DATO\u2019 SERI DIRAJA ",
    'SENATOR DATUK SERI DR. ', 'SENATOR DATUK SERI ',
    'SENATOR DR. ', 'SENATOR ',
    # Diraja / Utama / Amar
    "DATO' SERI DIRAJA DR. ", "DATO' SERI DIRAJA ",
    "DATO\u2019 SERI DIRAJA DR. ", "DATO\u2019 SERI DIRAJA ",
    "DATO' SERI UTAMA ", "DATO\u2019 SERI UTAMA ",
    'DATUK AMAR HAJI ', 'DATUK AMAR ',
    'DATUK TS. ',
    # Standard Dato/Datuk variants
    "DATO' WIRA DR. ", "DATO' WIRA ",
    "DATO' SERI DR. ", "DATO' SERI ", "DATO' SRI DR. ", "DATO' SRI ",
    "DATO' DR. ",      "DATO' ",
    'DATO\u2019 SERI DR. ', 'DATO\u2019 SERI ', 'DATO\u2019 SRI ', 'DATO\u2019 DR. ', 'DATO\u2019 ',
    'DATO\u2018 SERI DR. ', 'DATO\u2018 SERI ', 'DATO\u2018 SRI ', 'DATO\u2018 DR. ', 'DATO\u2018 ',
    'DATO SERI DR. ', 'DATO SERI ', 'DATO SRI DR. ', 'DATO SRI ',
    'DATUK SERI DR. ', 'DATUK SERI ', 'DATUK DR. ', 'DATUK ',
    'TAN SRI ', 'TUN ',
    'DR. ', 'DR ',   # 'DR ' (no dot) used in some informal/before-reshuffle lists
    'IR. ', 'TS. ',
    'TUAN HAJI ', 'TUAN ', 'PUAN HAJJAH ', 'PUAN ',
    'HAJI ', 'HAJJAH ', 'HAJAH ',
    'UTAMA ',
    'A/P ', 'A/L ',
    'PANGLIMA ',
]

def _strip_titles(name: str) -> str:
    n = name.strip()
    changed = True
    while changed:
        changed = False
        for t in sorted(_STRIP_TITLES, key=len, reverse=True):
            if n.upper().startswith(t.upper()):
                n = n[len(t):].strip()
                changed = True
    return n


def _normalise_key(name: str) -> str:
    k = _strip_titles(name).upper()
    k = re.sub(r"DATO['\u2019\u2018]\s*(?:SERI\s+|SRI\s+)?", '', k)
    k = re.sub(r'\bBINTE\b', 'BINTI', k)
    k = re.sub(r'\s+', ' ', k).strip()
    return k


@st.cache_data(show_spinner=False)
def build_mp_lookup(excel_bytes: bytes) -> dict:
    df = pd.read_excel(io.BytesIO(excel_bytes))
    name_col  = next(c for c in df.columns if 'NAMA' in c.upper() or 'NAME' in c.upper())
    const_col = next(c for c in df.columns if 'KAWASAN' in c.upper() or 'CONST' in c.upper()
                                                or 'PARLIMEN' in c.upper())

    lookup, tokens_index, first_index = {}, {}, {}

    for _, row in df.iterrows():
        raw   = str(row[name_col]).strip()
        const = str(row[const_col]).strip().title()
        key   = _normalise_key(raw)
        entry = {'constituency': const, 'clean_name': _strip_titles(raw).title()}
        lookup[key] = entry
        tokens = key.split()
        if tokens:
            tokens_index.setdefault(tokens[-1], []).append((key, entry))
            if len(tokens) >= 2:
                tokens_index.setdefault(' '.join(tokens[-2:]), []).append((key, entry))
            first_index.setdefault(tokens[0], []).append((key, entry))

    return {'lookup': lookup, 'tokens': tokens_index, 'first': first_index}


def lookup_mp(pdf_name: str, indexes: dict):
    if not indexes:
        return None, None
    lookup, tokens_index, first_index = indexes['lookup'], indexes['tokens'], indexes['first']

    k = _normalise_key(pdf_name)
    if k in lookup:
        return lookup[k], 'exact'

    k_nb = re.sub(r'\bBINTI\b\s*', '', k).strip()
    for lk, entry in lookup.items():
        if re.sub(r'\bBINTI\b\s*', '', lk).strip() == k_nb and k_nb:
            return entry, 'binti_normalised'

    tokens = k.split()
    if tokens:
        cands = tokens_index.get(tokens[-1], [])
        if len(cands) == 1:
            return cands[0][1], 'last_token'
        cands = first_index.get(tokens[0], [])
        if len(cands) == 1:
            return cands[0][1], 'first_token'
    return None, None



# ============================================================
# MINISTER LOOKUP  (supports before & after reshuffle rosters)
# ============================================================

def _nobin_key(k: str) -> str:
    """Strip BIN/BINTI from a normalised key — needed for informal name lists
    (before-reshuffle) that omit bin/binti from names."""
    k = re.sub(r'\bBIN\b\s*', '', k)
    k = re.sub(r'\bBINTI\b\s*', '', k)
    return re.sub(r'\s+', ' ', k).strip()


def _parse_minister_file(df: pd.DataFrame, cabinet_version: str) -> list[dict]:
    """
    Parse any of three minister Excel formats into a flat list of person dicts.

    Format A — formal (after reshuffle):
        Columns: Kementerian | Menteri | Timbalan Menteri
        Names have YAB/YB prefixes and full bin/binti forms.

    Format B — informal (first reshuffle / before reshuffle):
        Columns: Kementerian/Jabatan | Menteri | Timbalan Menteri
        Names have partial titles, no bin/binti; some cells have
        parenthetical notes like "(Timbalan Menteri Kewangan)".

    Format C — original cabinet (parsed from Hansard text):
        Columns: Jawatan | Nama | Kawasan Parlimen | Is_Deputy
        One row per person; Jawatan is the full role string.
    """
    cols = df.columns.tolist()
    cols_upper = [c.upper() for c in cols]

    # ── Detect Format C: has 'NAMA' and 'JAWATAN' columns ───────────────────
    if any('NAMA' in c for c in cols_upper) and any('JAWATAN' in c for c in cols_upper):
        nama_col       = next(c for c in cols if 'NAMA'       in c.upper())
        jawatan_col    = next(c for c in cols if 'JAWATAN'    in c.upper())
        kawasan_col    = next((c for c in cols if 'KAWASAN'   in c.upper()), None)
        kementerian_col = next((c for c in cols if 'KEMENTERIAN' in c.upper()), None)
        senator_col    = next((c for c in cols if 'SENATOR'   in c.upper()), None)
        timbalan_col_c = next((c for c in cols if 'TIMBALAN'  in c.upper()), None)

        records = []
        for _, row in df.iterrows():
            raw     = str(row[nama_col]).strip()
            jawatan = str(row[jawatan_col]).strip()
            kawasan = str(row.get(kawasan_col, '')).strip() if kawasan_col else ''

            if raw in ('', 'nan') or jawatan in ('', 'nan'):
                continue

            constituency = '' if kawasan in ('', 'nan', '-', '—') else kawasan.title()

            # Standardised format: Jawatan = 'Menteri' or 'Timbalan Menteri',
            #                      Kementerian = ministry name separately
            # Old format: Jawatan = full role string e.g. 'Menteri Pengangkutan'
            if kementerian_col:
                # New standardised format
                ministry   = str(row.get(kementerian_col, '')).strip()
                is_deputy  = jawatan.lower().strip() == 'timbalan menteri'
                role_label = 'Timbalan Menteri' if is_deputy else 'Menteri'
            else:
                # Old format — jawatan IS the full ministry description
                ministry   = jawatan
                is_deputy  = bool(re.match(r'^Timbalan', jawatan, re.IGNORECASE))
                role_label = 'Timbalan Menteri' if is_deputy else 'Menteri'

            # Senator: check dedicated column first, then fall back to name scan
            if senator_col:
                is_senator = str(row.get(senator_col, '')).strip().lower() in ('ya', 'yes', 'true', '1')
            else:
                is_senator = 'SENATOR' in raw.upper()

            records.append({
                'raw'            : raw,
                'ministry'       : ministry,
                'role_label'     : role_label,
                'is_deputy'      : is_deputy,
                'is_senator'     : is_senator,
                'constituency'   : constituency,
                'cabinet_version': cabinet_version,
            })
        return records

    # ── Formats A & B: Kementerian | Menteri | Timbalan Menteri ─────────────
    ministry_col = cols[0]
    menteri_col  = next((c for c in cols if c.strip() == 'Menteri'), None)
    timbalan_col = next((c for c in cols if 'Timbalan' in c), None)

    records = []
    for _, row in df.iterrows():
        ministry = str(row[ministry_col]).strip()
        if ministry in ('nan', ''):
            continue

        for col, role_label, is_deputy in [
            (menteri_col,  'Menteri',          False),
            (timbalan_col, 'Timbalan Menteri', True),
        ]:
            if col is None:
                continue
            raw = str(row.get(col, '')).strip()
            if raw in ('', 'nan', '-', '—'):
                continue

            # Strip parenthetical role annotations  e.g. "(Timbalan Menteri Kewangan)"
            raw = re.sub(r'\(.*?\)', '', raw).strip()
            if not raw:
                continue

            is_senator = 'SENATOR' in raw.upper()

            records.append({
                'raw'            : raw,
                'ministry'       : ministry,
                'role_label'     : role_label,
                'is_deputy'      : is_deputy,
                'is_senator'     : is_senator,
                'constituency'   : '',
                'cabinet_version': cabinet_version,
            })

    return records


@st.cache_data(show_spinner=False)
def build_minister_lookup(
    original_bytes: Optional[bytes] = None,
    before_bytes:   Optional[bytes] = None,
    after_bytes:    Optional[bytes] = None,
) -> dict:
    """
    Build a unified minister lookup from up to three Excel files:
      - original_bytes : original cabinet (DR-19122022 Hansard list)
      - before_bytes   : cabinet before first reshuffle
      - after_bytes    : cabinet after final reshuffle

    Priority on key collision (highest wins):  after > before > original
    cabinet_version tracks which roster(s) a person appears in.

    Indexes built:
      lookup        : normalised_key (with bin)      -> entry
      nobin_lookup  : normalised_key (without bin)   -> entry
      tokens_index  : last/suffix tokens             -> [(key, entry)]
      first_index   : first_token                    -> [(key, entry)]
    """
    all_records: list[dict] = []

    if original_bytes:
        df = pd.read_excel(io.BytesIO(original_bytes))
        all_records += _parse_minister_file(df, 'original')

    if before_bytes:
        df = pd.read_excel(io.BytesIO(before_bytes))
        all_records += _parse_minister_file(df, 'first_reshuffle')

    if after_bytes:
        df = pd.read_excel(io.BytesIO(after_bytes))
        all_records += _parse_minister_file(df, 'final_reshuffle')

    # Sort so highest-priority version is processed last (wins on key collision)
    VERSION_ORDER = {'original': 0, 'first_reshuffle': 1, 'final_reshuffle': 2}
    all_records.sort(key=lambda r: VERSION_ORDER.get(r['cabinet_version'], 0))

    lookup, nobin_lookup, tokens_index, first_index = {}, {}, {}, {}

    for rec in all_records:
        raw = rec['raw']
        key     = _normalise_key(raw)
        nb_key  = _nobin_key(key)

        jawatan = f"{rec['role_label']} — {rec['ministry']}"

        entry = {
            'jawatan'         : jawatan,
            'ministry'        : rec['ministry'],
            'role_label'      : rec['role_label'],
            'is_deputy'       : rec['is_deputy'],
            'is_senator'      : rec['is_senator'],
            'cabinet_version' : rec['cabinet_version'],
            'constituency'    : rec.get('constituency', ''),
            'clean_name'      : _strip_titles(raw).title(),
        }

        # Track which versions this person appears in
        existing = lookup.get(key) or nobin_lookup.get(nb_key)
        if existing and existing['cabinet_version'] != rec['cabinet_version']:
            # Collect all versions present
            prev_versions = set(existing['cabinet_version'].split('+'))
            prev_versions.add(rec['cabinet_version'])
            combined_ver = '+'.join(sorted(prev_versions, key=lambda v: VERSION_ORDER.get(v, 0)))
            entry['cabinet_version'] = combined_ver
            # Update all stored references to the same person
            for d in (lookup, nobin_lookup):
                for stored_entry in d.values():
                    if stored_entry is existing:
                        stored_entry['cabinet_version'] = combined_ver

        lookup[key]          = entry
        nobin_lookup[nb_key] = entry

        tokens = key.split()
        if tokens:
            tokens_index.setdefault(tokens[-1], []).append((key, entry))
            if len(tokens) >= 2:
                tokens_index.setdefault(' '.join(tokens[-2:]), []).append((key, entry))
                # Index on all-but-first-token to handle English given names
                # e.g. "ANTHONY LOKE SIEW FOOK" -> also index "LOKE SIEW FOOK"
                suffix = ' '.join(tokens[1:])
                tokens_index.setdefault(suffix, []).append((key, entry))
            first_index.setdefault(tokens[0], []).append((key, entry))

    return {
        'lookup'      : lookup,
        'nobin_lookup': nobin_lookup,
        'tokens'      : tokens_index,
        'first'       : first_index,
    }


def lookup_minister(pdf_name: str, indexes: dict):
    """
    Match a PDF speaker name against the combined minister roster.
    Returns (entry_dict, method_string) or (None, None).

    Match strategies (in order):
      1. exact       — normalised key with bin/binti
      2. nobin       — key with bin/binti stripped (for informal before-reshuffle names)
      3. binti_norm  — strip BINTI from both sides (women's name variants)
      4. last_token  — unambiguous family-name suffix
      5. first_token — unambiguous given-name
    """
    if not indexes:
        return None, None

    lookup       = indexes.get('lookup', {})
    nobin_lookup = indexes.get('nobin_lookup', {})
    tokens_index = indexes.get('tokens', {})
    first_index  = indexes.get('first', {})

    k    = _normalise_key(pdf_name)
    k_nb = _nobin_key(k)

    if k in lookup:
        return lookup[k], 'exact'

    if k_nb in nobin_lookup:
        return nobin_lookup[k_nb], 'nobin'

    # BINTI-normalised
    k_binti = re.sub(r'\bBINTI\b\s*', '', k).strip()
    for lk, entry in lookup.items():
        if re.sub(r'\bBINTI\b\s*', '', lk).strip() == k_binti and k_binti:
            return entry, 'binti_normalised'

    tokens = k.split()
    if tokens:
        cands = tokens_index.get(tokens[-1], [])
        if len(cands) == 1:
            return cands[0][1], 'last_token'
        cands = first_index.get(tokens[0], [])
        if len(cands) == 1:
            return cands[0][1], 'first_token'

    return None, None



# Character class for speaker names; includes / for Indian "a/l", "a/p" patronymics
_CHAR = r"[a-zA-Z\s\(\)@\-\'\u2018\u2019\./]"

SPEAKER_RE = re.compile(
    rf"^([A-Z]{_CHAR}+?)(?:\s*\[([^\]]*)\])?\s*:\s*(.*)",
    re.MULTILINE | re.DOTALL,
)
UNCLOSED_RE = re.compile(
    rf"^([A-Z]{_CHAR}+?)\s*\[([A-Z]{_CHAR}+?)\s*:\s*(.*)",
    re.MULTILINE | re.DOTALL,
)
# Detects a speaker line embedded INSIDE a multi-line block
EMBEDDED_SPEAKER_RE = re.compile(
    rf"(?:^|\n)([A-Z]{_CHAR}+?(?:\s*\[[^\]]*\])?\s*:\s)",
    re.MULTILINE,
)
HEADER_RE   = re.compile(r"DR\.\s*\d+\.\s*\d+\.\s*\d+")
PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*$")

_NAME_SIGNALS = ('bin ', 'binti ', 'Dato', 'Datuk', 'Tan Sri', 'Tun ', 'Dr. ')


def _is_personal_name(text: str) -> bool:
    return any(s in text for s in _NAME_SIGNALS)


def _is_header_only_block(text: str) -> bool:
    """A block containing only page-number + 'DR.XX.XX.XXXX' header lines."""
    s = text.strip()
    if not s:
        return True
    if s.startswith('\u25a0'):
        return True
    lines = [l.strip() for l in s.split('\n') if l.strip()]
    for line in lines:
        if PAGE_NUM_RE.match(line):
            continue
        if HEADER_RE.search(line) and len(line) < 30:
            continue
        return False
    return True


def _clean_speech_text(text: str) -> str:
    """Strip page-header noise and tidy whitespace inside speech text."""
    # Combined headers: "<num>\nDR.XX.XX.XXXX" or reverse
    text = re.sub(r'\n\s*\d{1,3}\s*\n\s*DR\.\s*\d+\.\s*\d+\.\s*\d+\s*', '\n', text)
    text = re.sub(r'\n\s*DR\.\s*\d+\.\s*\d+\.\s*\d+\s*\n\s*\d{1,3}\s*', '\n', text)
    # Any remaining "DR.XX.XX.XXXX" anywhere
    text = re.sub(r'DR\.\s*\d+\.\s*\d+\.\s*\d+', '', text)
    # Standalone page numbers on their own line
    text = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', text)
    # Whitespace cleanup
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def _parse_block(text: str):
    """Parse a block into {speaker, role, constituency, speech}, or None."""
    m = SPEAKER_RE.match(text)
    if m:
        outer  = m.group(1).replace('\n', ' ').strip()
        bracket = (m.group(2) or '').replace('\n', ' ').strip()
        speech  = (m.group(3) or '').strip()
        if bracket and _is_personal_name(bracket):
            return dict(speaker=bracket, role=outer, constituency='', speech=speech)
        return dict(speaker=outer, role='', constituency=bracket, speech=speech)

    m2 = UNCLOSED_RE.match(text)
    if m2:
        outer  = m2.group(1).replace('\n', ' ').strip()
        bracket = m2.group(2).replace('\n', ' ').strip()
        speech  = (m2.group(3) or '').strip()
        if _is_personal_name(bracket):
            return dict(speaker=bracket, role=outer, constituency='', speech=speech)
        return dict(speaker=outer, role='', constituency=bracket, speech=speech)
    return None


def _split_block_by_speakers(text: str):
    """
    Split a multi-line block at points where a new speaker line begins
    mid-block. Returns [(segment_text, parsed_dict_or_None)] with the
    first segment always being the original block opening.
    """
    matches = [m for m in EMBEDDED_SPEAKER_RE.finditer(text) if m.start() > 0]
    if not matches:
        return [(text, None)]

    segments = []
    last = 0
    for m in matches:
        segments.append(text[last:m.start()])
        new_start = m.start() + 1 if text[m.start()] == '\n' else m.start()
        last = new_start
    segments.append(text[last:])

    result = [(segments[0], None)]
    for seg in segments[1:]:
        result.append((seg, _parse_block(seg)))
    return result


def process_hansard_pdf(
    file_bytes: bytes,
    start_page: int,
    end_page: int,
    mp_indexes: Optional[dict] = None,
    minister_indexes: Optional[dict] = None,
) -> list:
    transcript: list = []
    pdf_const_lookup: dict[str, str] = {}

    cur_speaker = cur_role = cur_const = cur_match = cur_portfolio = ''
    cur_is_minister = cur_is_deputy = cur_cabinet_ver = ''
    cur_speech: list = []
    cur_page = 1

    def _flush():
        if cur_speaker:
            transcript.append({
                'Speaker'         : cur_speaker,
                'Role'            : cur_role,
                'Portfolio'       : cur_portfolio,
                'Is_Minister'     : cur_is_minister,
                'Is_Deputy'       : cur_is_deputy,
                'Cabinet_Version' : cur_cabinet_ver,
                'Constituency'    : cur_const,
                'Roster_Match'    : cur_match,
                'Speech'          : _clean_speech_text('\n'.join(cur_speech)),
                'Page'            : cur_page,
            })

    def _start_new(parsed, page_idx):
        nonlocal cur_speaker, cur_role, cur_const, cur_match, cur_speech, cur_page
        nonlocal cur_portfolio, cur_is_minister, cur_is_deputy, cur_cabinet_ver
        cur_speaker = parsed['speaker']
        cur_page    = page_idx + 1

        pdf_const = parsed['constituency']

        # ── Minister lookup ────────────────────────────────────────────────
        min_entry, min_method = lookup_minister(cur_speaker, minister_indexes or {})
        if min_entry:
            cur_role        = parsed['role'] if parsed['role'] else min_entry['jawatan']
            cur_portfolio   = min_entry['jawatan']
            cur_is_minister = 'Yes'
            cur_is_deputy   = 'Yes' if min_entry.get('is_deputy') else ''
            cur_cabinet_ver = min_entry.get('cabinet_version', '')
        else:
            cur_role        = parsed['role']
            cur_portfolio   = ''
            cur_is_minister = ''
            cur_is_deputy   = ''
            cur_cabinet_ver = ''

        # ── Constituency resolution ────────────────────────────────────────
        mp_entry, mp_method = lookup_mp(cur_speaker, mp_indexes or {})

        if pdf_const:
            cur_const = pdf_const.title()
            cur_match = (min_method or mp_method) or '—'
            pdf_const_lookup[cur_speaker] = cur_const
        elif min_entry and min_entry['constituency']:
            # Ministers have constituency in the minister Excel
            cur_const = min_entry['constituency']
            cur_match = min_method
        elif mp_entry:
            cur_const = mp_entry['constituency']
            cur_match = mp_method
        else:
            cur_const = ''
            cur_match = '—'

        cur_speech = [parsed['speech']] if parsed['speech'] else []

    with fitz.open(stream=file_bytes, filetype='pdf') as doc:
        start_idx = max(0, start_page - 1)
        end_idx   = min(len(doc), end_page)
        cur_page  = start_idx + 1

        for i in range(start_idx, end_idx):
            for block in doc[i].get_text('blocks'):
                text = block[4].strip()
                if not text:
                    continue
                if _is_header_only_block(text):
                    continue

                segments = _split_block_by_speakers(text)

                for idx, (seg_text, seg_parsed) in enumerate(segments):
                    if idx == 0:
                        first_parsed = _parse_block(seg_text)
                        if first_parsed:
                            _flush()
                            _start_new(first_parsed, i)
                        elif cur_speaker:
                            cur_speech.append(seg_text.replace('\n', ' '))
                    else:
                        _flush()
                        if seg_parsed:
                            _start_new(seg_parsed, i)

        _flush()

    # Back-fill constituencies from within-document observations
    for entry in transcript:
        if not entry['Constituency'] and entry['Speaker'] in pdf_const_lookup:
            entry['Constituency'] = pdf_const_lookup[entry['Speaker']]
            if entry['Roster_Match'] == '—':
                entry['Roster_Match'] = 'backfill'
        # Back-fill minister portfolio for entries where minister was seen later
        if not entry['Portfolio']:
            min_entry, _ = lookup_minister(entry['Speaker'], minister_indexes or {})
            if min_entry:
                entry['Portfolio']        = min_entry['jawatan']
                entry['Is_Minister']      = 'Yes'
                entry['Is_Deputy']        = 'Yes' if min_entry.get('is_deputy') else ''
                entry['Cabinet_Version']  = min_entry.get('cabinet_version', '')

    return transcript


# ============================================================
# Normalize Speaker Names
# ============================================================
_NORMALIZE_TITLES = [
    'Yang Berhormat ', 'Yang Amat Berhormat ',
    "Dato\u2019 Seri ", "Dato\u2018 Seri ",
    "Dato' Seri ", "Dato' Sri ", 'Datuk Seri ',
    'Datuk ', "Dato\u2019 ", "Dato\u2018 ", "Dato' ",
    'Tan Sri ', 'Tun ',
    'Dr. ', 'Tuan ', 'Puan ',
    'Haji ', 'Hajjah ',
    'Panglima ', 'Ir. ', 'Ts. ',
]

def normalize_speakers(transcript):
    for entry in transcript:
        clean = entry['Speaker']
        for t in _NORMALIZE_TITLES:
            clean = re.compile(re.escape(t), re.IGNORECASE).sub('', clean)
        entry['Normalized_Speaker'] = clean.strip()
    return transcript


# ============================================================
# Excel Export
# ============================================================
def dataframe_to_xlsx(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transcript')
    return output.getvalue()


# ============================================================
# UI
# ============================================================
st.markdown("<h1>Hansard <span>Extractor</span></h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:var(--text-mute);margin-bottom:1.5rem;'>"
    "V7 — three-cabinet minister roster (original + two reshuffles)</p>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("MP Roster (optional)")
    st.caption(
        "Upload the Dewan Rakyat member list Excel to enrich constituency detection. "
        "Expected columns: **NAMA PENUH** and **KAWASAN PARLIMEN**."
    )
    roster_file = st.file_uploader("Upload MP roster (.xlsx)", type=["xlsx"], key="roster")

    st.divider()

    st.header("Minister Roster (optional)")
    st.caption(
        "Upload any or all three cabinet lists. They are merged automatically — "
        "each minister is tagged with which cabinet(s) they appear in. "
        "Expected columns: **Jawatan** | **Nama** | **Kawasan Parlimen** (original) "
        "or **Kementerian** | **Menteri** | **Timbalan Menteri** (reshuffle lists)."
    )
    minister_original_file = st.file_uploader(
        "📂 Original cabinet — DR 19.12.2022 (.xlsx)",
        type=["xlsx"], key="ministers_original"
    )
    minister_before_file = st.file_uploader(
        "📂 After first reshuffle (.xlsx)",
        type=["xlsx"], key="ministers_before"
    )
    minister_after_file = st.file_uploader(
        "📂 After final reshuffle (.xlsx)",
        type=["xlsx"], key="ministers_after"
    )

mp_indexes: dict = {}
if roster_file:
    with st.spinner("Building MP lookup…"):
        mp_indexes = build_mp_lookup(roster_file.read())
    st.sidebar.success(f"MP roster loaded — {len(mp_indexes['lookup'])} MPs indexed.")

minister_indexes: dict = {}
if minister_original_file or minister_before_file or minister_after_file:
    with st.spinner("Building minister lookup…"):
        minister_indexes = build_minister_lookup(
            original_bytes=minister_original_file.read() if minister_original_file else None,
            before_bytes  =minister_before_file.read()   if minister_before_file   else None,
            after_bytes   =minister_after_file.read()    if minister_after_file    else None,
        )
    n_total  = len(minister_indexes['lookup'])
    versions = []
    if minister_original_file: versions.append("original")
    if minister_before_file:   versions.append("first reshuffle")
    if minister_after_file:    versions.append("final reshuffle")
    st.sidebar.success(
        f"Minister roster loaded — {n_total} ministers indexed "
        f"({', '.join(versions)})."
    )

uploaded_files = st.file_uploader(
    "Drag & Drop up to 5 Hansard PDFs",
    type=["pdf"],
    accept_multiple_files=True,
)

DISPLAY_COLS = [
    "Speaker", "Normalized_Speaker", "Role", "Portfolio",
    "Is_Minister", "Is_Deputy", "Cabinet_Version",
    "Constituency", "Roster_Match",
    "Speech", "Page", "Document_Name",
]

if uploaded_files:
    if len(uploaded_files) > 5:
        st.error("Maximum 5 Hansard PDFs allowed.")
    else:
        # ── Page count info panel ────────────────────────────────────────────
        st.subheader("Documents")
        st.caption("All pages will be processed. Page counts are shown for reference.")

        # Read page counts without re-reading bytes later
        file_infos = []
        for file in uploaded_files:
            raw = file.read()
            with fitz.open(stream=raw, filetype="pdf") as doc:
                n_pages = len(doc)
            file_infos.append({
                "file"    : file,
                "bytes"   : raw,
                "name"    : file.name,
                "stem"    : file.name.rsplit(".", 1)[0],   # filename without .pdf
                "pages"   : n_pages,
            })

        # Show a compact info card per file (up to 5 cols)
        info_cols = st.columns(len(file_infos))
        for col, fi in zip(info_cols, file_infos):
            with col:
                st.metric(
                    label=fi["name"] if len(fi["name"]) <= 20 else fi["name"][:18] + "…",
                    value=f"{fi['pages']} pages",
                )

        # ── Process ──────────────────────────────────────────────────────────
        if st.button("🚀 Process All Documents", width="stretch"):
            with st.spinner("Extracting text, cleaning speech, detecting speakers…"):
                # per-file dataframes so we can export individually
                per_file_dfs: dict[str, pd.DataFrame] = {}
                has_error = False

                for fi in file_infos:
                    try:
                        data = process_hansard_pdf(
                            fi["bytes"], 1, fi["pages"], mp_indexes, minister_indexes
                        )
                        for item in data:
                            item["Document_Name"] = fi["name"]
                        per_file_dfs[fi["stem"]] = pd.DataFrame(data)
                    except Exception as ex:
                        st.error(f"Failed processing {fi['name']}: {ex}")
                        has_error = True
                        break

                if not has_error:
                    combined_df = pd.concat(per_file_dfs.values(), ignore_index=True)

                    if combined_df.empty:
                        st.warning(
                            "No speaker segments found across any of the uploaded PDFs."
                        )
                        st.stop()

                    # Normalize names across the combined set
                    combined_df = pd.DataFrame(
                        normalize_speakers(combined_df.to_dict("records"))
                    )
                    # Also normalize per-file DFs
                    for stem, df_file in per_file_dfs.items():
                        per_file_dfs[stem] = pd.DataFrame(
                            normalize_speakers(df_file.to_dict("records"))
                        )

                    # ── Summary metrics (combined) ────────────────────────────
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    c1.metric("Total segments",    len(combined_df))
                    c2.metric("Unique speakers",   combined_df["Speaker"].nunique())
                    c3.metric("Ministers tagged",
                               int((combined_df["Is_Minister"] == "Yes").sum()))
                    c4.metric("With constituency",
                               int((combined_df["Constituency"] != "").sum()))
                    c5.metric("With role tag",
                               int((combined_df["Role"] != "").sum()))
                    c6.metric("Roster-matched",
                               int((combined_df["Roster_Match"] != "—").sum()))

                    st.success(
                        f"Processing complete — {len(combined_df)} speech segments "
                        f"across {len(per_file_dfs)} document(s)."
                    )

                    # ── Filter ────────────────────────────────────────────────
                    with st.expander("🔎 Filter results"):
                        speakers = sorted(combined_df["Speaker"].unique().tolist())
                        sel_speakers = st.multiselect("Filter by speaker", speakers)
                        view_df = (
                            combined_df[combined_df["Speaker"].isin(sel_speakers)]
                            if sel_speakers else combined_df
                        )

                    # ── Preview (combined, filtered) ──────────────────────────
                    st.subheader("Data Preview")
                    st.dataframe(
                        view_df[DISPLAY_COLS], width="stretch", height=420
                    )

                    # ── Export ────────────────────────────────────────────────
                    st.subheader("Export")

                    # Combined JSON (all files together)
                    st.download_button(
                        "📥 Download combined JSON (all files)",
                        data=combined_df[DISPLAY_COLS].to_json(
                            orient="records", indent=4, force_ascii=False
                        ),
                        file_name="hansard_combined.json",
                        mime="application/json",
                        width="stretch",
                    )

                    st.markdown("**Individual XLSX — one per PDF:**")

                    # Up to 5 individual download buttons, named after the PDF
                    xlsx_cols = st.columns(len(per_file_dfs))
                    for col, (stem, df_file) in zip(xlsx_cols, per_file_dfs.items()):
                        with col:
                            xlsx_name = f"{stem}.xlsx"
                            st.download_button(
                                f"📥 {stem[:18]}…" if len(stem) > 18 else f"📥 {stem}",
                                data=dataframe_to_xlsx(df_file[DISPLAY_COLS]),
                                file_name=xlsx_name,
                                mime=(
                                    "application/vnd.openxmlformats-officedocument"
                                    ".spreadsheetml.sheet"
                                ),
                                key=f"dl_{stem}",
                            )
