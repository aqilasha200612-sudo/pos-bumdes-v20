from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime
import gspread
import os
import urllib.parse
from jinja2 import Template

app = FastAPI(title="POS BUMDes Kembaran Versi 54 (Full Google Sheets - Fast Sync)")

SPREADSHEET_ID = "1nYcOD2tJ006gv9HnzSKi-tbjYLaC9nbGUuKiY02BwAI"
STATIC_QRIS = "00020101021126590013ID.CO.BNI.WWW011893600009150484690802096175577690303UMI51450015ID.OR.GPNQR.WWW0215ID10266064913750303UMI5204544153033605802ID5915BUMDES KEMBARAN6008BANYUMAS61055318263049AFA"

def safe_float(val) -> float:
    if val is None or val == "": return 0.0
    val_str = str(val).strip().replace(' ', '').replace('Rp', '').replace('rp', '').replace('RP', '')
    if not val_str: return 0.0
    if val_str.count('.') > 1: val_str = val_str.replace('.', '')
    if val_str.count(',') > 1: val_str = val_str.replace(',', '')
    if ',' in val_str and '.' in val_str:
        if val_str.rfind(',') > val_str.rfind('.'): val_str = val_str.replace(',', '')
        else: val_str = val_str.replace('.', '').replace(',', '.')
    elif ',' in val_str: val_str = val_str.replace(',', '.')
    elif '.' in val_str:
        if len(val_str.split('.')[-1]) == 3: val_str = val_str.replace('.', '')
    try: return float(val_str)
    except ValueError: return 0.0

def create_dynamic_qris(base_qris: str, amount: float) -> str:
    if amount <= 0: return base_qris
    amount_str = str(int(amount))
    tag_54 = f"54{len(amount_str):02d}{amount_str}"
    idx = base_qris.find("5802ID")
    if idx == -1: return base_qris
    new_qris = base_qris[:idx] + tag_54 + base_qris[idx:-4]
    crc = 0xFFFF
    for char in new_qris:
        crc ^= ord(char) << 8
        for _ in range(8):
            if (crc & 0x8000) > 0: crc = (crc << 1) ^ 0x1021
            else: crc = crc << 1
        crc &= 0xFFFF
    return new_qris + f"{crc:04X}"

def get_gspread_sheet(sheet_name="DataPemesan"):
    if not os.path.exists("credentials.json"): 
        print("ERROR: credentials.json tidak ditemukan di server!")
        return None
    try:
        client = gspread.service_account(filename="credentials.json")
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        try: return spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            if sheet_name == "Config":
                sheet = spreadsheet.add_worksheet(title="Config", rows=10, cols=10)
                sheet.append_row(["Kuota Promo", "Persen Diskon", "Tanggal Panen", "WA Admin Utama", "WA Admin Keuangan", "WA Admin Kebun", "Harga Per Kg"])
                sheet.append_row([100, 10, "2026-11-15", "628123456789", "628123456790", "628123456791", 52500])
                return sheet
            elif sheet_name == "POS":
                sheet = spreadsheet.add_worksheet(title="POS", rows=100, cols=12)
                sheet.append_row(["ID POS", "Tanggal", "Tipe Transaksi", "ID Referensi PO", "Nama Pelanggan", "Qty Golden", "Qty White", "Diskon", "Total Tagihan", "Dibayar", "Kembalian", "Metode Pembayaran"])
                return sheet
            elif sheet_name == "Stok_Kebun":
                sheet = spreadsheet.add_worksheet(title="Stok_Kebun", rows=100, cols=8)
                sheet.append_row(["ID Stok", "Lajur", "Baris", "Jenis Buah", "Berat", "Status", "ID Pesanan", "Nama Pemesan"])
                return sheet
            elif sheet_name == "DataPemesan":
                sheet = spreadsheet.add_worksheet(title="DataPemesan", rows=100, cols=21)
                sheet.append_row(["ID Pesanan", "Tanggal", "Nama Pelanggan", "No WhatsApp", "Keterangan", "Total Tagihan", "Nominal DP", "DP Diterima", "Status DP", "Qty Golden", "Qty White", "Lajur Golden", "Baris Golden", "Lajur White", "Baris White", "Aktual Golden", "Aktual White", "Status Pelunasan"])
                return sheet
            return None
    except Exception as e: 
        print("Gagal akses Google Sheets:", e)
        return None

def get_all_records_safe(sheet_name: str):
    sheet = get_gspread_sheet(sheet_name)
    if not sheet: return []
    try:
        records = sheet.get_all_values()
        if len(records) < 2: return []
        headers = [str(h).strip() for h in records[0]]
        data = []
        for row in records[1:]:
            row_padded = row + [""] * (len(headers) - len(row))
            data.append(dict(zip(headers, row_padded)))
        return data
    except Exception as e:
        print(f"Error parse {sheet_name}:", e)
        return []

def get_app_config():
    records = get_all_records_safe("Config")
    if records:
        conf = records[0]
        try: conf['Harga Per Kg'] = safe_float(conf.get('Harga Per Kg', '52500'))
        except: conf['Harga Per Kg'] = 52500.0
        return conf
    return {"Kuota Promo": 100, "Persen Diskon": 0.0, "Tanggal Panen": "Segera", "WA Admin Utama": "628123456789", "WA Admin Keuangan": "628123456790", "WA Admin Kebun": "628123456791", "Harga Per Kg": 52500.0}

# ======================= HTML TEMPLATES =======================
PRE_ORDER_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Pre-Order BUMDes Kembaran</title><script src="https://cdn.tailwindcss.com"></script><script>tailwind.config = { theme: { extend: { colors: { shopee: '#EE4D2D' } } } }</script></head>
<body class="bg-gray-100 pb-20">
    <header class="bg-shopee text-white p-4 shadow-md sticky top-0 z-50"><div class="max-w-md mx-auto flex justify-between items-center"><h1 class="font-bold text-lg">Pre-Order BUMDes Kembaran</h1><a href="/admin" class="text-xs bg-white text-shopee px-2.5 py-1 rounded font-bold shadow">Admin</a></div></header>
    <main class="max-w-md mx-auto bg-white min-h-screen pb-10">
        <div class="flex justify-center p-4 bg-gray-50 border-b"><img src="https://lh3.googleusercontent.com/d/1ZljExg4TXAp_DAQXrJEQJCjS_wjTLFAY" class="h-24 object-contain"></div>
        {% set kuota_promo = config.get('Kuota Promo', 0)|int %}
        {% set ada_promo = kuota_promo > 0 %}
        {% set persen_diskon = config.get('Persen Diskon', 0.0)|float if ada_promo else 0.0 %}
        {% set harga_asli = config.get('Harga Per Kg', 52500.0)|float %}
        {% set harga_diskon = harga_asli - (harga_asli * (persen_diskon / 100.0)) %}
        <div class="w-full {% if ada_promo %}bg-orange-100 text-shopee{% else %}bg-gray-200 text-gray-700{% endif %} p-2 text-[11px] font-semibold text-center border-b">
            Panen Raya: {{ config.get('Tanggal Panen', '-') }} | Estimasi Berat: ~1.5 Kg / Butir<br>
            {% if ada_promo %} Sisa Kuota Promo: {{ kuota_promo }} Transaksi {% else %} Kuota Promo Habis (Harga Normal) {% endif %}
        </div>
        <form action="/submit-order" method="POST" class="p-4 space-y-4">
            <div class="grid grid-cols-2 gap-4">
                <div class="border rounded-lg shadow-sm p-3 relative bg-white flex flex-col justify-between">
                    <div class="absolute top-0 left-0 bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-br-lg font-bold">Golden Humi</div>
                    <div class="mt-5 flex justify-center"><img src="https://lh3.googleusercontent.com/d/1E7kjiNX0RfAHoysDqtyce-WiKWM72KMn" class="h-24 w-24 object-cover rounded-md mb-2 shadow-sm"></div>
                    <div class="text-center"><h2 class="text-xs font-bold text-gray-800">Melon Golden</h2>
                    {% if ada_promo and persen_diskon > 0 %}<div class="text-[10px] text-gray-400 line-through mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div><div class="text-shopee font-bold text-sm">Rp {{ "{:,.0f}".format(harga_diskon) }}/Kg</div>{% else %}<div class="text-shopee font-bold text-sm mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div>{% endif %}</div>
                    <div class="mt-3"><label class="text-[10px] font-bold text-gray-500 block text-center">Jumlah (Butir)</label><input type="number" step="1" name="qty_golden" id="qty_golden" value="0" min="0" onchange="hitungTotal()" onkeyup="hitungTotal()" class="w-full border rounded p-1.5 text-lg font-bold text-center mt-1 focus:border-shopee"><div class="text-[10px] text-gray-500 text-center mt-1">Est: <span id="est_golden">0</span> Kg</div></div>
                </div>
                <div class="border rounded-lg shadow-sm p-3 relative bg-white flex flex-col justify-between">
                    <div class="absolute top-0 left-0 bg-emerald-500 text-white text-[10px] px-2 py-0.5 rounded-br-lg font-bold">White Humi</div>
                    <div class="mt-5 flex justify-center"><img src="https://lh3.googleusercontent.com/d/1MYZFh0OqnNjPE113wQWONrbxhpoEIwtm" class="h-24 w-24 object-cover rounded-md mb-2 shadow-sm"></div>
                    <div class="text-center"><h2 class="text-xs font-bold text-gray-800">Melon White</h2>
                    {% if ada_promo and persen_diskon > 0 %}<div class="text-[10px] text-gray-400 line-through mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div><div class="text-shopee font-bold text-sm">Rp {{ "{:,.0f}".format(harga_diskon) }}/Kg</div>{% else %}<div class="text-shopee font-bold text-sm mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div>{% endif %}</div>
                    <div class="mt-3"><label class="text-[10px] font-bold text-gray-500 block text-center">Jumlah (Butir)</label><input type="number" step="1" name="qty_white" id="qty_white" value="0" min="0" onchange="hitungTotal()" onkeyup="hitungTotal()" class="w-full border rounded p-1.5 text-lg font-bold text-center mt-1 focus:border-shopee"><div class="text-[10px] text-gray-500 text-center mt-1">Est: <span id="est_white">0</span> Kg</div></div>
                </div>
            </div>
            <div class="bg-blue-50 border border-blue-200 p-3 rounded-xl space-y-1 mt-2 shadow-sm">
                <div class="flex justify-between items-center text-xs text-blue-800 font-semibold"><span>Estimasi Total Berat:</span> <span id="tampil_est_berat" class="font-bold">0.0 KG</span></div>
                <div class="flex justify-between items-center"><div><div class="text-xs text-blue-700 font-semibold">Estimasi Tagihan:</div><div class="text-base font-black text-blue-900" id="tampil_total">Rp 0</div></div><div class="text-right"><div class="text-xs text-orange-600 font-semibold">DP Wajib (50%):</div><div class="text-base font-black text-orange-600" id="tampil_dp">Rp 0</div></div></div>
            </div>
            <div class="bg-gray-50 p-4 rounded-xl border space-y-3 mt-4">
                <div><label class="text-xs text-gray-600 font-semibold block mb-1">Nama Lengkap</label><input type="text" name="nama_pelanggan" required class="w-full p-2 border rounded text-sm focus:border-shopee"></div>
                <div><label class="text-xs text-gray-600 font-semibold block mb-1">WhatsApp Aktif</label><input type="tel" name="no_whatsapp" required class="w-full p-2 border rounded text-sm focus:border-shopee"></div>
                <div><label class="text-xs text-gray-600 font-semibold block mb-1">Keterangan (Opsional)</label><textarea name="keterangan" class="w-full p-2 border rounded text-sm focus:border-shopee" rows="2"></textarea></div>
            </div>
            <button type="submit" class="w-full bg-shopee text-white font-bold py-3.5 rounded-lg shadow-lg text-sm transition mt-2">Pesan Sekarang & Bayar DP 🚀</button>
        </form>
    </main>
    <script>
        const hargaAktual = {{ harga_diskon if ada_promo else harga_asli }};
        function hitungTotal() {
            let qG = parseInt(document.getElementById('qty_golden').value) || 0;
            let qW = parseInt(document.getElementById('qty_white').value) || 0;
            let estBeratG = qG * 1.5; let estBeratW = qW * 1.5;
            let totalEstBerat = estBeratG + estBeratW;
            let total = totalEstBerat * hargaAktual;
            document.getElementById('est_golden').innerText = estBeratG.toFixed(1);
            document.getElementById('est_white').innerText = estBeratW.toFixed(1);
            document.getElementById('tampil_est_berat').innerText = totalEstBerat.toFixed(1) + ' KG';
            document.getElementById('tampil_total').innerText = 'Rp ' + total.toLocaleString('id-ID');
            document.getElementById('tampil_dp').innerText = 'Rp ' + (total/2).toLocaleString('id-ID');
        }
    </script>
</body>
</html>
"""

SUCCESS_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Berhasil Pesan</title><script src="https://cdn.tailwindcss.com"></script><script>tailwind.config = { theme: { extend: { colors: { shopee: '#EE4D2D' } } } }</script></head>
<body class="bg-gray-100 min-h-screen p-4 flex items-center justify-center">
    <div class="max-w-md w-full bg-white rounded-2xl shadow-md p-6 text-center space-y-4">
        <div class="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center text-3xl mx-auto">✓</div>
        <h1 class="font-bold text-xl text-gray-800">Pre-Order Berhasil Dicatat!</h1>
        <p class="text-xs text-gray-500">ID Pesanan: <span class="font-mono font-bold text-shopee text-sm">{{ id_pesanan }}</span></p>
        <div class="bg-gray-50 p-4 rounded-xl border text-left text-xs space-y-2">
            <div class="flex justify-between"><span>Nama:</span><span class="font-bold">{{ nama_pelanggan }}</span></div>
            <div class="flex justify-between"><span>Jumlah:</span><span class="font-bold">Golden: {{ qtyg }} | White: {{ qtyw }}</span></div>
            <div class="flex justify-between"><span>Estimasi Tagihan:</span><span class="font-bold">Rp {{ "{:,.0f}".format(tot) }}</span></div>
            <div class="flex justify-between text-shopee font-bold text-sm border-t pt-2"><span>DP Wajib (50%):</span><span>Rp {{ "{:,.0f}".format(dp) }}</span></div>
        </div>
        <div class="bg-blue-50 border border-blue-200 p-4 rounded-xl">
            <p class="text-xs font-bold text-blue-800 mb-2">Scan QRIS untuk Pembayaran DP:</p>
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={{ qris_url_encoded }}" class="h-44 w-44 mx-auto object-contain bg-white p-2 border rounded">
        </div>
        <a href="{{ wa_link }}" target="_blank" class="block w-full bg-green-500 hover:bg-green-600 text-white font-bold py-3 rounded-lg text-sm shadow">💬 Konfirmasi Pembayaran via WhatsApp</a>
        <a href="/pre-order" class="block text-xs text-gray-500 font-semibold hover:underline pt-2">← Buat Pesanan Baru</a>
    </div>
</body>
</html>
"""

# ======================= ENDPOINTS =======================

@app.get("/", response_class=HTMLResponse)
def root(): return RedirectResponse(url="/pre-order")

@app.get("/pre-order", response_class=HTMLResponse)
def pre_order_page(): return HTMLResponse(content=Template(PRE_ORDER_HTML).render(config=get_app_config()))

@app.post("/submit-order")
def submit_order(
    nama_pelanggan: str = Form(...), no_whatsapp: str = Form(...), keterangan: str = Form(""),
    qty_golden: float = Form(0.0), qty_white: float = Form(0.0)
):
    config = get_app_config()
    kuota_promo = int(safe_float(config.get("Kuota Promo", 0)))
    harga = safe_float(config.get("Harga Per Kg", 52500))
    diskon_persen = safe_float(config.get("Persen Diskon", 0)) if kuota_promo > 0 else 0.0
    harga_setelah_diskon = harga - (harga * (diskon_persen / 100.0))
    
    total = float((qty_golden + qty_white) * 1.5 * harga_setelah_diskon)
    dp = float(total * 0.5)
    id_pes = f"PO-{datetime.now().strftime('%d%H%M%S')}"
    tgl = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    sheet = get_gspread_sheet("DataPemesan")
    if sheet:
        sheet.append_row([id_pes, tgl, nama_pelanggan, no_whatsapp, keterangan or "-", total, dp, 0.0, "Belum", qty_golden, qty_white, "-", 0, "-", 0, 0, 0, "Belum"])
        if kuota_promo > 0:
            sheet_conf = get_gspread_sheet("Config")
            if sheet_conf:
                try: sheet_conf.update_cell(2, 1, kuota_promo - 1)
                except: pass
                
    # Direct URL Bypass untuk QRIS (Anti Delay)
    url = f"/success?id={id_pes}&dp={dp}&nama={urllib.parse.quote(nama_pelanggan)}&qtyg={qty_golden}&qtyw={qty_white}&tot={total}"
    return RedirectResponse(url=url, status_code=303)

@app.get("/success", response_class=HTMLResponse)
def success_page(id: str, dp: float = 0.0, nama: str = "Pelanggan", qtyg: float = 0.0, qtyw: float = 0.0, tot: float = 0.0):
    config = get_app_config()
    wa = str(config.get("WA Admin Keuangan", "628123456790")).strip()
    if wa.startswith('0'): wa = '62' + wa[1:]
    elif not wa.startswith('62'): wa = '62' + wa
    
    dq = urllib.parse.quote(create_dynamic_qris(STATIC_QRIS, dp))
    pesan_wa = f"Halo Admin Keuangan, saya sudah transfer DP sebesar Rp {dp:,.0f} untuk ID Pesanan {id}."
    wa_link = f"https://api.whatsapp.com/send?phone={wa}&text={urllib.parse.quote(pesan_wa)}"
    
    return HTMLResponse(content=Template(SUCCESS_HTML).render(id_pesanan=id, nama_pelanggan=nama, dp=dp, qtyg=int(qtyg), qtyw=int(qtyw), tot=tot, qris_url_encoded=dq, wa_link=wa_link))

@app.get("/api/qris")
def get_qris_api(amount: float):
    dq = create_dynamic_qris(STATIC_QRIS, amount)
    return {"qris_string": dq, "qris_url": f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(dq)}"}

# ================= ADMIN PAGES (RINGKASAN) =================
@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    records = get_all_records_safe("DataPemesan")
    pl = []
    t_dp, lunas_count, belum_count = 0.0, 0, 0
    for r in records:
        if not r.get("ID Pesanan"): continue
        dp_terima = safe_float(r.get("DP Diterima"))
        status_dp = str(r.get("Status DP", "Belum"))
        t_dp += dp_terima
        if status_dp == "Sudah": lunas_count += 1
        else: belum_count += 1
        pl.append({
            "id_pesanan": r.get("ID Pesanan"), "tanggal_transaksi": r.get("Tanggal"),
            "nama_pelanggan": r.get("Nama Pelanggan"), "no_whatsapp": r.get("No WhatsApp"),
            "qty_golden": safe_float(r.get("Qty Golden")), "qty_white": safe_float(r.get("Qty White")),
            "total_tagihan": safe_float(r.get("Total Tagihan")), "nominal_dp": safe_float(r.get("Nominal DP")),
            "nominal_dp_diterima": dp_terima, "status_dp": status_dp, "status_pelunasan": r.get("Status Pelunasan")
        })
    
    html = """<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8"><title>Admin Panel</title><script src="https://cdn.tailwindcss.com"></script></head><body class="p-6 bg-gray-50"><div class="max-w-7xl mx-auto space-y-6"><h1 class="text-2xl font-bold">Admin Pusat (Full GSheets)</h1><div class="flex space-x-2"><a href="/admin-kebun" class="bg-emerald-600 text-white px-4 py-2 rounded font-bold text-sm">👨‍🌾 Admin Kebun</a><a href="/laporan" class="bg-purple-600 text-white px-4 py-2 rounded font-bold text-sm">📊 Laporan Jual</a><a href="/pos" class="bg-blue-600 text-white px-4 py-2 rounded font-bold text-sm">🛒 Kasir POS</a></div><div class="grid grid-cols-4 gap-4"><div class="bg-white p-4 border rounded shadow">Total PO: <span class="font-bold">{{ pl|length }}</span></div><div class="bg-white p-4 border rounded shadow text-green-700">Lunas DP: <span class="font-bold">{{ lunas }}</span></div><div class="bg-white p-4 border rounded shadow text-red-700">Menunggu DP: <span class="font-bold">{{ belum }}</span></div><div class="bg-white p-4 border rounded shadow text-amber-700">Total DP: <span class="font-bold">Rp {{ "{:,.0f}".format(td) }}</span></div></div><div class="bg-white p-4 border rounded"><h2 class="font-bold mb-4">Daftar Pesanan</h2><table class="w-full text-left text-sm"><thead><tr class="border-b"><th>ID</th><th>Nama</th><th>Qty (G/W)</th><th>Est Tagihan</th><th>DP Diterima</th><th>Aksi</th></tr></thead><tbody>{% for p in pl %}<tr class="border-b hover:bg-gray-50"><td>{{ p.id_pesanan }}</td><td>{{ p.nama_pelanggan }}<br><span class="text-blue-500">{{ p.no_whatsapp }}</span></td><td>{{ p.qty_golden|int }} / {{ p.qty_white|int }}</td><td>Rp {{ "{:,.0f}".format(p.total_tagihan) }}<br><span class="text-orange-500 text-[10px]">DP: Rp {{ "{:,.0f}".format(p.nominal_dp) }}</span></td><td><form action="/update-dp-diterima/{{ p.id_pesanan }}" method="POST" class="flex"><input type="number" name="nominal_dp_diterima" value="{{ p.nominal_dp_diterima }}" class="border p-1 w-24 text-xs"><button class="bg-green-600 text-white px-2 text-xs ml-1 rounded">Save</button></form></td><td>{% if p.status_dp == 'Sudah' %}<span class="text-green-600 font-bold">✅ Lunas</span>{% else %}<form action="/konfirmasi-dp/{{ p.id_pesanan }}" method="POST"><button class="bg-blue-500 text-white px-2 py-1 text-xs rounded">Acc DP</button></form>{% endif %}</td></tr>{% endfor %}</tbody></table></div></div></body></html>"""
    return HTMLResponse(Template(html).render(pl=pl, lunas=lunas_count, belum=belum_count, td=t_dp))

@app.get("/admin-kebun", response_class=HTMLResponse)
def admin_kebun_page():
    po_records = get_all_records_safe("DataPemesan")
    pl = [r for r in po_records if r.get("Status DP") == "Sudah" and r.get("Status Pelunasan") != "Sudah Lunas"]
    
    html = """<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8"><title>Admin Kebun</title><script src="https://cdn.tailwindcss.com"></script></head><body class="p-6 bg-emerald-50"><div class="max-w-5xl mx-auto space-y-4"><h1 class="text-2xl font-bold text-emerald-800">👨‍🌾 Admin Kebun</h1><a href="/admin" class="text-sm bg-gray-200 px-3 py-1 rounded">← Kembali</a><div class="bg-white p-4 border rounded mt-4"><h2 class="font-bold">Daftar PO Siap Panen (Sudah DP)</h2><ul class="mt-2 space-y-2">{% for p in pl %}<li class="p-3 border rounded"><b>{{ p['ID Pesanan'] }}</b> - {{ p['Nama Pelanggan'] }} (Golden: {{ p['Qty Golden'] }}, White: {{ p['Qty White'] }})</li>{% endfor %}</ul></div></div></body></html>"""
    return HTMLResponse(Template(html).render(pl=pl))

@app.get("/laporan", response_class=HTMLResponse)
def laporan_page():
    pos_records = get_all_records_safe("POS")
    html = """<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8"><title>Laporan Jual</title><script src="https://cdn.tailwindcss.com"></script></head><body class="p-6 bg-gray-50"><div class="max-w-5xl mx-auto space-y-4"><h1 class="text-2xl font-bold">📊 Laporan Penjualan (Live)</h1><a href="/admin" class="text-sm bg-gray-200 px-3 py-1 rounded">← Kembali</a><div class="bg-white p-4 border rounded"><table class="w-full text-left text-sm"><thead><tr class="border-b"><th>ID POS</th><th>Tipe</th><th>Nama</th><th>Total</th><th>Metode</th></tr></thead><tbody>{% for t in trx %}<tr class="border-b"><td>{{ t['ID POS'] }}<br><span class="text-xs text-gray-400">{{ t['Tanggal'] }}</span></td><td>{{ t['Tipe Transaksi'] }}</td><td>{{ t['Nama Pelanggan'] }}</td><td class="font-bold">Rp {{ t['Total Tagihan'] }}</td><td>{{ t['Metode Pembayaran'] }}</td></tr>{% endfor %}</tbody></table></div></div></body></html>"""
    return HTMLResponse(Template(html).render(trx=reversed(pos_records)))

@app.get("/pos", response_class=HTMLResponse)
def pos_page():
    html = """<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8"><title>Kasir POS</title><script src="https://cdn.tailwindcss.com"></script></head><body class="p-6 bg-blue-50 flex items-center justify-center min-h-screen"><div class="bg-white p-8 rounded-xl shadow-lg text-center"><h1 class="text-2xl font-black text-blue-700 mb-2">🛒 KASIR POS BUMDES</h1><p class="text-sm text-gray-500 mb-4">Fitur ini terhubung langsung ke Google Sheets</p><a href="/admin" class="bg-gray-800 text-white px-4 py-2 rounded font-bold">← Kembali ke Admin</a></div></body></html>"""
    return HTMLResponse(html)

@app.post("/update-dp-diterima/{id_pesanan}")
def update_dp_diterima(id_pesanan: str, nominal_dp_diterima: float = Form(...)):
    sheet = get_gspread_sheet("DataPemesan")
    if sheet:
        records = sheet.get_all_values()
        for i, row in enumerate(records[1:], start=2):
            if len(row) > 0 and row[0] == id_pesanan:
                nom_dp = safe_float(row[6]) if len(row) > 6 else 0.0
                sheet.update_cell(i, 8, nominal_dp_diterima)
                sheet.update_cell(i, 9, "Sudah" if nominal_dp_diterima >= nom_dp else "Belum")
                break
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/konfirmasi-dp/{id_pesanan}")
def konfirmasi_dp(id_pesanan: str):
    sheet = get_gspread_sheet("DataPemesan")
    if sheet:
        records = sheet.get_all_values()
        for i, row in enumerate(records[1:], start=2):
            if len(row) > 0 and row[0] == id_pesanan:
                nom_dp = safe_float(row[6]) if len(row) > 6 else 0.0
                sheet.update_cell(i, 8, nom_dp)
                sheet.update_cell(i, 9, "Sudah")
                break
    return RedirectResponse(url="/admin", status_code=303)
