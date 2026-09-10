import os
import re
import glob
import logging
from typing import Dict, Any, Optional, Tuple, List
import pandas as pd
from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_SALES_MODEL, DATASETS_DIR
from sales_prompt import SALES_AI_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)

class SalesDataLoader:
    """Excel va CSV ma'lumotlarini yuklovchi va boshqaruvchi kesh mexanizmi"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SalesDataLoader, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.report_df: Optional[pd.DataFrame] = None
        self.gear_df: Optional[pd.DataFrame] = None
        self.joined_df: Optional[pd.DataFrame] = None
        self.report_filename: str = ""
        self.gear_filename: str = ""
        self.report_sheet: str = ""
        self.gear_sheet: str = ""
        self.load_data()
        self.initialized = True

    def load_data(self):
        """datasets papkasidan fayllarni topib yuklaydi"""
        report_files = glob.glob(os.path.join(DATASETS_DIR, "report*.xlsx")) + glob.glob(os.path.join(DATASETS_DIR, "report*.csv"))
        gear_files = glob.glob(os.path.join(DATASETS_DIR, "Gear*.xlsx")) + glob.glob(os.path.join(DATASETS_DIR, "*gear*.xlsx"))

        if report_files:
            rep_path = report_files[0]
            self.report_filename = os.path.basename(rep_path)
            try:
                if rep_path.endswith('.csv'):
                    self.report_df = pd.read_csv(rep_path)
                    self.report_sheet = "CSV"
                else:
                    xl = pd.ExcelFile(rep_path)
                    self.report_sheet = xl.sheet_names[0]
                    self.report_df = pd.read_excel(rep_path, sheet_name=0)
                logger.info(f"Loaded report: {self.report_filename} ({len(self.report_df)} rows)")
            except Exception as e:
                logger.error(f"Error loading report {rep_path}: {e}")

        if gear_files:
            gear_path = gear_files[0]
            self.gear_filename = os.path.basename(gear_path)
            try:
                xl = pd.ExcelFile(gear_path)
                self.gear_sheet = xl.sheet_names[0]
                self.gear_df = pd.read_excel(gear_path, sheet_name=0)
                logger.info(f"Loaded gear list: {self.gear_filename} ({len(self.gear_df)} rows)")
            except Exception as e:
                logger.error(f"Error loading gear {gear_path}: {e}")

        self._merge_data()

    def _merge_data(self):
        """report va Gear_list ni JOIN qiladi: report['Магазин №'] == gear['Код магазина'] / gear['Прикрепить к ИД магазина']"""
        if self.report_df is not None and self.gear_df is not None:
            rep = self.report_df.copy()
            gear = self.gear_df.copy()

            rep['Магазин №_clean'] = rep['Магазин №'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
            
            # Gear list dan store ID larni tayyorlaymiz
            # Ham 'Код магазина', ham 'Прикрепить к ИД магазина' ni hisobga olamiz
            gear_records = []
            for _, row in gear.iterrows():
                store_id1 = str(row.get('Код магазина', '')).strip().replace('.0', '')
                store_id2 = str(row.get('Прикрепить к ИД магазина', '')).strip().replace('.0', '')
                territory = row.get('Территория')
                filial = row.get('Филиал')
                agent_gear = row.get('Ответственный агент магазина')
                
                if store_id1 and store_id1 != 'nan':
                    gear_records.append({'store_id': store_id1, 'Территория': territory, 'Филиал': filial, 'Ответственный агент магазина': agent_gear})
                if store_id2 and store_id2 != 'nan' and store_id2 != store_id1:
                    gear_records.append({'store_id': store_id2, 'Территория': territory, 'Филиал': filial, 'Ответственный агент магазина': agent_gear})
            
            gear_mapped = pd.DataFrame(gear_records).drop_duplicates(subset=['store_id'])

            self.joined_df = rep.merge(
                gear_mapped,
                left_on='Магазин №_clean',
                right_on='store_id',
                how='left'
            )
            logger.info(f"Merged joined_df ready ({len(self.joined_df)} rows, matched territories: {self.joined_df['Территория'].notna().sum()})")
        elif self.report_df is not None:
            self.joined_df = self.report_df.copy()

    def reload(self):
        """Keshni yangilaydi"""
        self.load_data()


# Global loader
data_loader = SalesDataLoader()


def get_available_agents() -> List[str]:
    """Mavjud agentlar ro'yxatini qaytaradi"""
    if data_loader.report_df is not None and 'Документ Отв.агент' in data_loader.report_df.columns:
        agents = data_loader.report_df['Документ Отв.агент'].dropna().unique().tolist()
        return [str(a).strip() for a in agents if str(a).strip()]
    return []


def find_matching_agent(query: str) -> Optional[str]:
    """Foydalanuvchi so'rovidan qaysi agent so'ralayotganini topadi"""
    agents = get_available_agents()
    query_lower = query.lower()
    
    # Aniq yoki qisman moslikni tekshirish
    for agent in agents:
        agent_clean = agent.lower()
        # "Фуркат Курбанов (Сам)" -> "Фуркат Курбанов", "Фуркат", "Курбанов"
        words = re.sub(r'[\(\)]', '', agent_clean).split()
        if agent_clean in query_lower:
            return agent
        if len(words) >= 2 and all(w in query_lower for w in words[:2]):
            return agent
            
    # Bitta so'z bo'yicha ham tekshiramiz (agar unikal bo'lsa)
    for agent in agents:
        agent_clean = agent.lower()
        words = [w for w in re.sub(r'[\(\)]', '', agent_clean).split() if len(w) > 3]
        for w in words:
            if w in query_lower:
                return agent
    return None


def calculate_abc(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Mijozlar bo'yicha ABC klassifikatsiyasini hisoblaydi:
    A: 0 - 70%
    B: 70 - 90%
    C: 90 - 100%
    """
    if 'Магазин Название' not in df.columns or 'Сумма факт' not in df.columns:
        return pd.DataFrame(), {}

    # Mijoz bo'yicha guruhlash
    client_sales = df.groupby(['Магазин №', 'Магазин Название'])['Сумма факт'].sum().reset_index()
    client_sales = client_sales.sort_values(by='Сумма факт', ascending=False).reset_index(drop=True)

    total_sales = client_sales['Сумма факт'].sum()
    if total_sales <= 0:
        total_sales = 1.0  # nolga bo'lishdan himoya

    client_sales['Ulush_%'] = (client_sales['Сумма факт'] / total_sales) * 100
    client_sales['Kumulyativ_%'] = client_sales['Ulush_%'].cumsum()

    def assign_category(cum):
        if cum <= 70.0001:
            return 'A'
        elif cum <= 90.0001:
            return 'B'
        else:
            return 'C'

    client_sales['Kategoriya'] = client_sales['Kumulyativ_%'].apply(assign_category)

    # Statistika
    summary = {
        'total_clients': len(client_sales),
        'total_sales': float(df['Сумма факт'].sum()),
        'count_A': int((client_sales['Kategoriya'] == 'A').sum()),
        'count_B': int((client_sales['Kategoriya'] == 'B').sum()),
        'count_C': int((client_sales['Kategoriya'] == 'C').sum()),
        'sales_A': float(client_sales[client_sales['Kategoriya'] == 'A']['Сумма факт'].sum()),
        'sales_B': float(client_sales[client_sales['Kategoriya'] == 'B']['Сумма факт'].sum()),
        'sales_C': float(client_sales[client_sales['Kategoriya'] == 'C']['Сумма факт'].sum()),
    }
    return client_sales, summary


def calculate_regions(df: pd.DataFrame) -> pd.DataFrame:
    """Hududlar (Территория va Филиал) kesimida savdo tahlili"""
    if 'Территория' not in df.columns or 'Сумма факт' not in df.columns:
        return pd.DataFrame()

    valid_df = df.dropna(subset=['Территория']).copy()
    if valid_df.empty:
        return pd.DataFrame()

    reg_group = valid_df.groupby('Территория').agg(
        Jami_Savdo=('Сумма факт', 'sum'),
        Mijozlar_Soni=('Магазин №', 'nunique'),
        Sotuvlar_Soni=('Сумма факт', 'count')
    ).reset_index()

    total_reg_sales = reg_group['Jami_Savdo'].sum()
    if total_reg_sales > 0:
        reg_group['Ulush_%'] = (reg_group['Jami_Savdo'] / total_reg_sales) * 100
    else:
        reg_group['Ulush_%'] = 0.0

    reg_group['Ortacha_Mijoz_Savdosi'] = reg_group['Jami_Savdo'] / reg_group['Mijozlar_Soni'].replace(0, 1)
    reg_group = reg_group.sort_values(by='Jami_Savdo', ascending=False).reset_index(drop=True)
    return reg_group


def calculate_skus(df: pd.DataFrame, top_n: int = 15) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """SKU / Mahsulotlar tahlili"""
    if 'Продукт Название' not in df.columns or 'Сумма факт' not in df.columns:
        return pd.DataFrame(), {}

    sku_group = df.groupby('Продукт Название').agg(
        Jami_Miqdor=('Колв. продуктов факт', 'sum'),
        Jami_Savdo=('Сумма факт', 'sum')
    ).reset_index()

    total_sales = sku_group['Jami_Savdo'].sum()
    if total_sales > 0:
        sku_group['Ulush_%'] = (sku_group['Jami_Savdo'] / total_sales) * 100
    else:
        sku_group['Ulush_%'] = 0.0

    sku_group = sku_group.sort_values(by='Jami_Savdo', ascending=False).reset_index(drop=True)
    
    summary = {
        'total_unique_skus': len(sku_group),
        'total_quantity': float(df['Колв. продуктов факт'].sum()) if 'Колв. продуктов факт' in df.columns else 0,
        'total_sales': float(total_sales)
    }
    return sku_group, summary


def check_negative_values(df: pd.DataFrame) -> Dict[str, Any]:
    """Manfiy qiymatlarni aniqlash"""
    if 'Сумма факт' not in df.columns:
        return {'has_negative': False}

    neg_df = df[df['Сумма факт'] < 0]
    if neg_df.empty:
        return {'has_negative': False}

    return {
        'has_negative': True,
        'count': len(neg_df),
        'total_negative_sum': float(neg_df['Сумма факт'].sum()),
        'samples': neg_df[['Магазин Название', 'Продукт Название', 'Сумма факт']].head(5).to_dict(orient='records')
    }


def prepare_rag_context(user_query: str) -> Dict[str, Any]:
    """
    Foydalanuvchi savoliga qarab RAG qidiruvi va hisob-kitoblarini bajaradi.
    Tegishli agent, hudud, SKU yoki ABC parametrlarini tanlaydi.
    """
    loader = SalesDataLoader()
    df = loader.joined_df
    if df is None or df.empty:
        return {
            'found': False,
            'message': "Ma'lumotlar bazasi yoki fayllar yuklanmagan."
        }

    # 1. Agent bormi?
    target_agent = find_matching_agent(user_query)
    
    context_data: Dict[str, Any] = {
        'found': True,
        'user_query': user_query,
        'target_agent': target_agent,
        'sources': []
    }

    # Asosiy ishchi dataframe
    working_df = df.copy()
    if target_agent:
        working_df = working_df[working_df['Документ Отв.агент'] == target_agent]

    # Source ma'lumotlari
    source_report = {
        'file': loader.report_filename,
        'sheet': loader.report_sheet,
        'total_rows': len(loader.report_df) if loader.report_df is not None else 0,
        'filtered_rows': len(working_df),
        'columns': "Документ Отв.агент, Дата по дням, Документ №, Продукт Название, Магазин №, Магазин Название, Колв. продуктов факт, Сумма факт"
    }
    context_data['sources'].append(source_report)

    if loader.gear_df is not None:
        source_gear = {
            'file': loader.gear_filename,
            'sheet': loader.gear_sheet,
            'total_rows': len(loader.gear_df),
            'join_key': "report['Магазин №'] = Gear_list['Код магазина']",
            'columns': "Наименование магазина, Ответственный агент магазина, Территория, Филиал, Код магазина"
        }
        context_data['sources'].append(source_gear)

    # Manfiy summalar
    neg_info = check_negative_values(working_df)
    context_data['negatives'] = neg_info

    # Hisob-kitoblar
    # 1-AGENT: Mijozlar / ABC
    client_sales, abc_summary = calculate_abc(working_df)
    context_data['abc_summary'] = abc_summary
    if not client_sales.empty:
        context_data['top_clients'] = client_sales.head(10).to_dict(orient='records')
        # A, B, C dan namunalar
        context_data['sample_a_clients'] = client_sales[client_sales['Kategoriya'] == 'A'].head(5)[['Магазин Название', 'Сумма факт', 'Ulush_%']].to_dict(orient='records')

    # 2-AGENT: Hududlar
    reg_df = calculate_regions(working_df)
    if not reg_df.empty:
        context_data['regions'] = reg_df.to_dict(orient='records')
    else:
        context_data['regions'] = "Ushbu ma'lumotda hudud bo'yicha ma'lumot mavjud emas"

    # 3-AGENT: SKU
    sku_df, sku_summary = calculate_skus(working_df)
    context_data['sku_summary'] = sku_summary
    if not sku_df.empty:
        context_data['top_skus'] = sku_df.head(10).to_dict(orient='records')
        context_data['low_skus'] = sku_df.tail(5).to_dict(orient='records')

    return context_data


def format_context_for_llm(context: Dict[str, Any]) -> str:
    """RAG natijalarini LLM uchun aniq matn holatiga keltiradi"""
    if not context.get('found'):
        return "RAG RETRIEVAL RESULT: Ma'lumot topilmadi."

    lines = []
    lines.append("=== RAG RETRIEVAL & EXACT CALCULATIONS RESULT ===")
    lines.append(f"Foydalanuvchi so'rovi: {context['user_query']}")
    if context.get('target_agent'):
        lines.append(f"Tanlangan Agent: {context['target_agent']}")
    else:
        lines.append("Umumiy tahlil (barcha agentlar bo'yicha)")

    # ABC / Mijozlar
    abc = context.get('abc_summary', {})
    lines.append("\n[1-AGENT: MIJOZLAR / ABC HISOB-KITOBLARI]:")
    lines.append(f"- Jami mijozlar soni: {abc.get('total_clients', 0)}")
    lines.append(f"- Jami savdo summasi: {abc.get('total_sales', 0):,.2f}")
    lines.append(f"- A kategoriyadagi mijozlar soni: {abc.get('count_A', 0)} (Savdosi: {abc.get('sales_A', 0):,.2f})")
    lines.append(f"- B kategoriyadagi mijozlar soni: {abc.get('count_B', 0)} (Savdosi: {abc.get('sales_B', 0):,.2f})")
    lines.append(f"- C kategoriyadagi mijozlar soni: {abc.get('count_C', 0)} (Savdosi: {abc.get('sales_C', 0):,.2f})")
    
    top_c = context.get('top_clients', [])
    if top_c:
        lines.append("- TOP mijozlar:")
        for c in top_c[:7]:
            lines.append(f"  * {c['Магазин Название']}: {c['Сумма факт']:,.2f} ({c['Ulush_%']:.2f}%) [Kat: {c['Kategoriya']}]")

    # Hududlar
    lines.append("\n[2-AGENT: HUDUDLAR / TERRITORIYA HISOB-KITOBLARI]:")
    regs = context.get('regions')
    if isinstance(regs, list):
        for r in regs:
            lines.append(f"- Hudud: {r['Территория']} | Jami savdo: {r['Jami_Savdo']:,.2f} | Ulush: {r['Ulush_%']:.2f}% | Mijozlar: {r['Mijozlar_Soni']} ta | O'rtacha mijoz savdosi: {r['Ortacha_Mijoz_Savdosi']:,.2f}")
    else:
        lines.append(f"- {regs}")

    # SKU
    sku_sum = context.get('sku_summary', {})
    lines.append("\n[3-AGENT: SKU / MAHSULOT HISOB-KITOBLARI]:")
    lines.append(f"- Jami SKU soni: {sku_sum.get('total_unique_skus', 0)}")
    lines.append(f"- Jami mahsulot miqdori: {sku_sum.get('total_quantity', 0):,.2f}")
    lines.append(f"- Jami savdo: {sku_sum.get('total_sales', 0):,.2f}")
    top_s = context.get('top_skus', [])
    if top_s:
        lines.append("- TOP SKUlar:")
        for s in top_s[:7]:
            lines.append(f"  * {s['Продукт Название']}: Miqdor={s['Jami_Miqdor']:,.0f}, Summa={s['Jami_Savdo']:,.2f} ({s['Ulush_%']:.2f}%)")

    # Manfiy summalar
    negs = context.get('negatives', {})
    if negs.get('has_negative'):
        lines.append(f"\n[DIQQAT: MANFIY QIYMATLAR ANIQLANDI]:")
        lines.append(f"- Manfiy summalar soni: {negs['count']} ta, Jami manfiy summa: {negs['total_negative_sum']:,.2f}")
        lines.append("  (Manfiy summa qaytarish yoki korrektirovka bo'lishi mumkin, source'da sababi aniqlanmagan)")

    # Aniq Source ma'lumotlari
    lines.append("\n[MANBA VA JOIN METADATA (EXACT SOURCE)]:")
    for s in context.get('sources', []):
        lines.append(f"- File: {s.get('file')} | Sheet: {s.get('sheet')} | Filtered Rows: {s.get('filtered_rows', s.get('total_rows'))} | Columns: {s.get('columns')}")
        if 'join_key' in s:
            lines.append(f"  JOIN: {s['join_key']}")

    lines.append("=== RAG END ===")
    return "\n".join(lines)


def strip_source_section(text: str) -> str:
    """Javob oxiridagi ortiqcha SOURCE / MANBA bloklarini tozalab tashlaydi"""
    patterns = [
        r'\n*\s*#{1,4}\s*.*(?:EXACT\s*SOURCE|SOURCE|MANBA|MANBA\s*METADATASI).*$',
        r'\n*\s*[-─_]{3,}\s*\n*\s*(?:📌\s*)?(?:EXACT\s*SOURCE|SOURCE|MANBA).*$',
        r'\n*\s*(?:EXACT\s*SOURCE|SOURCE:|MANBA:).*$'
    ]
    cleaned = text
    for p in patterns:
        m = re.search(p, cleaned, flags=re.IGNORECASE | re.DOTALL)
        if m:
            cleaned = cleaned[:m.start()].strip()
    return cleaned.strip()


def format_to_telegram_html(text: str) -> str:
    """Markdown matnini Telegram xavfsiz HTML formatiga aylantiradi"""
    # 1. Source qismini olib tashlash
    text = strip_source_section(text)

    # 2. Xavfsiz HTML escape
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Sarlavhalar: ### Sarlavha -> <b>📌 Sarlavha</b>
    text = re.sub(r'^[ \t]*#{1,4}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Qalin matn: **bold** -> <b>bold</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # Inline kod: `code` -> <code>code</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Ro'yxat belgilari
    text = re.sub(r'^[ \t]*[\*\-]\s+', '• ', text, flags=re.MULTILINE)

    # Ajratuvchi chiziqlar
    text = re.sub(r'^[ \t]*---[ \t]*$', '────────────────────────', text, flags=re.MULTILINE)

    return text.strip()


async def ask_sales_ai(user_query: str) -> str:
    """
    Sales AI Orchestrator orqali foydalanuvchi savoliga to'liq javob tayyorlaydi.
    1. RAG retrieval & calculation
    2. Prompt validation
    3. Gemini AI generation
    4. Formatlash (Telegram HTML va Source tozalash)
    """
    try:
        context = prepare_rag_context(user_query)
        rag_text = format_context_for_llm(context)

        prompt_payload = f"""
Foydalanuvchi savoli:
{user_query}

Quyida RAG tizimi tomonidan Excel/CSV manbalaridan olingan aniq hisob-kitoblar keltirilgan:
{rag_text}

MUHIM KO'RSATMALAR:
1. Faqat berilgan aniq hisob-kitoblar va raqamlar asosida tahlil va AI xulosasi bering.
2. JAVOB OXIRIDA SOURCE / MANBA / FAYL NOMI / METADATA kabi bo'limlarni ASLO YOZMA! Ular mutlaqo shart emas.
3. Telegram uchun chiroyli va tushunarli tartibda bayon eting.
"""
        response = client.models.generate_content(
            model=GEMINI_SALES_MODEL,
            contents=[SALES_AI_SYSTEM_PROMPT, prompt_payload],
            config=types.GenerateContentConfig(temperature=0.2)
        )
        
        # Natijani tozalash va HTML formatiga keltirish
        raw_text = response.text or ""
        return format_to_telegram_html(raw_text)
    except Exception as e:
        logger.error(f"Error in ask_sales_ai: {e}")
        return f"❌ Tahlil jarayonida xatolik yuz berdi:\n<code>{str(e)}</code>"
