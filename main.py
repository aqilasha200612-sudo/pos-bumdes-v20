from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime
import gspread
import os
import urllib.parse
from jinja2 import Template

app = FastAPI(title="POS BUMDes Kembaran Versi 56 (Index-Based Sync)")

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
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(base_dir, "credentials.json")
    if not os.path.exists(cred_path): cred_path = "credentials.json"
    
    if not os.path.exists(cred_path): 
        return None
    try:
        client = gspread.service_account(filename=cred_path)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        try: return spreadsheet.worksheet(sheet_name)
        except Exception: return None
    except Exception as e:
        print("ERROR GSPREAD:", e)
        return None

def get_app_config():
    sheet = get_gspread_sheet("Config")
    if sheet:
        try:
            records = sheet.get_all_values()
            if len(records) > 1:
                row = records[1]
                return {
                    "Kuota Promo": int(safe_float(row[0] if len(row)>0 else 100)),
                    "Persen Diskon": safe_float(row[1] if len(row)>1 else 0),
                    "Tanggal Panen": str(row[2] if len(row)>2 else "Segera"),
                    "WA Admin Utama": str(row[3] if len(row)>3 else "628123456789"),
                    "WA Admin Keuangan": str(row[4] if len(row)>4 else "628123456790"),
                    "WA Admin Kebun": str(row[5] if len(row)>5 else "628123456791"),
                    "Harga Per Kg": safe_float(row[6] if len(row)>6 else 52500)
                }
        except Exception: pass
    return {"Kuota Promo": 100, "Persen Diskon": 0.0, "Tanggal Panen": "Segera", "WA Admin Utama": "628123456789", "WA Admin Keuangan": "628123456790", "WA Admin Kebun": "628123456791", "Harga Per Kg": 52500.0}

# ======================= HTML TEMPLATES =======================

PRE_ORDER_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Pre-Order BUMDes Kembaran</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config = { theme: { extend: { colors: { shopee: '#EE4D2D' } } } }</script>
</head>
<body class="bg-gray-100 pb-20">
    <header class="bg-shopee text-white p-4 shadow-md sticky top-0 z-50">
        <div class="max-w-md mx-auto flex justify-between items-center"><h1 class="font-bold text-lg">Pre-Order BUMDes Kembaran</h1><a href="/admin" class="text-xs bg-white text-shopee px-2.5 py-1 rounded font-bold shadow">Admin</a></div>
    </header>
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
                    <div class="text-center">
                        <h2 class="text-xs font-bold text-gray-800">Melon Golden</h2>
                        {% if ada_promo and persen_diskon > 0 %}<div class="text-[10px] text-gray-400 line-through mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div><div class="text-shopee font-bold text-sm">Rp {{ "{:,.0f}".format(harga_diskon) }}/Kg</div>{% else %}<div class="text-shopee font-bold text-sm mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div>{% endif %}
                    </div>
                    <div class="mt-3">
                        <label class="text-[10px] font-bold text-gray-500 block text-center">Jumlah (Butir)</label>
                        <input type="number" step="1" name="qty_golden" id="qty_golden" value="0" min="0" onchange="hitungTotal()" onkeyup="hitungTotal()" class="w-full border rounded p-1.5 text-lg font-bold text-center mt-1 focus:border-shopee">
                        <div class="text-[10px] text-gray-500 text-center mt-1">Est: <span id="est_golden">0</span> Kg</div>
                    </div>
                </div>
                <div class="border rounded-lg shadow-sm p-3 relative bg-white flex flex-col justify-between">
                    <div class="absolute top-0 left-0 bg-emerald-500 text-white text-[10px] px-2 py-0.5 rounded-br-lg font-bold">White Humi</div>
                    <div class="mt-5 flex justify-center"><img src="https://lh3.googleusercontent.com/d/1MYZFh0OqnNjPE113wQWONrbxhpoEIwtm" class="h-24 w-24 object-cover rounded-md mb-2 shadow-sm"></div>
                    <div class="text-center">
                        <h2 class="text-xs font-bold text-gray-800">Melon White</h2>
                        {% if ada_promo and persen_diskon > 0 %}<div class="text-[10px] text-gray-400 line-through mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div><div class="text-shopee font-bold text-sm">Rp {{ "{:,.0f}".format(harga_diskon) }}/Kg</div>{% else %}<div class="text-shopee font-bold text-sm mt-1">Rp {{ "{:,.0f}".format(harga_asli) }}/Kg</div>{% endif %}
                    </div>
                    <div class="mt-3">
                        <label class="text-[10px] font-bold text-gray-500 block text-center">Jumlah (Butir)</label>
                        <input type="number" step="1" name="qty_white" id="qty_white" value="0" min="0" onchange="hitungTotal()" onkeyup="hitungTotal()" class="w-full border rounded p-1.5 text-lg font-bold text-center mt-1 focus:border-shopee">
                        <div class="text-[10px] text-gray-500 text-center mt-1">Est: <span id="est_white">0</span> Kg</div>
                    </div>
                </div>
            </div>
            <div class="bg-blue-50 border border-blue-200 p-3 rounded-xl space-y-1 mt-2 shadow-sm">
                <div class="flex justify-between items-center text-xs text-blue-800 font-semibold"><span>Estimasi Total Berat:</span> <span id="tampil_est_berat" class="font-bold">0.0 KG</span></div>
                <div class="flex justify-between items-center">
                    <div><div class="text-xs text-blue-700 font-semibold">Estimasi Tagihan:</div><div class="text-base font-black text-blue-900" id="tampil_total">Rp 0</div></div>
                    <div class="text-right"><div class="text-xs text-orange-600 font-semibold">DP Wajib (50%):</div><div class="text-base font-black text-orange-600" id="tampil_dp">Rp 0</div></div>
                </div>
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
            let estBeratG = qG * 1.5;
            let estBeratW = qW * 1.5;
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
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Berhasil Pesan</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config = { theme: { extend: { colors: { shopee: '#EE4D2D' } } } }</script>
</head>
<body class="bg-gray-100 min-h-screen p-4 flex items-center justify-center">
    <div class="max-w-md w-full bg-white rounded-2xl shadow-md p-6 text-center space-y-4">
        <div class="w-16 h-16 bg-green-100 text-green-600 rounded-full flex items-center justify-center text-3xl mx-auto">✓</div>
        <h1 class="font-bold text-xl text-gray-800">Pre-Order Berhasil Dicatat!</h1>
        <p class="text-xs text-gray-500">ID Pesanan Anda: <span class="font-mono font-bold text-shopee text-sm">{{ order.id_pesanan }}</span></p>
        <div class="bg-gray-50 p-4 rounded-xl border text-left text-xs space-y-2">
            <div class="flex justify-between"><span>Nama:</span><span class="font-bold">{{ order.nama_pelanggan }}</span></div>
            <div class="flex justify-between"><span>WhatsApp:</span><span class="font-bold">{{ order.no_whatsapp }}</span></div>
            <div class="flex justify-between"><span>Jumlah:</span><span class="font-bold">Golden: {{ order.qty_golden|int }} | White: {{ order.qty_white|int }}</span></div>
            <div class="flex justify-between"><span>Estimasi Tagihan:</span><span class="font-bold">Rp {{ "{:,.0f}".format(order.total_tagihan) }}</span></div>
            <div class="flex justify-between text-shopee font-bold text-sm border-t pt-2"><span>DP Wajib (50%):</span><span>Rp {{ "{:,.0f}".format(order.nominal_dp) }}</span></div>
        </div>
        <div class="bg-blue-50 border border-blue-200 p-4 rounded-xl">
            <p class="text-xs font-bold text-blue-800 mb-2">Scan QRIS untuk Pembayaran DP:</p>
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={{ qris_url_encoded }}" class="h-44 w-44 mx-auto object-contain bg-white p-2 border rounded">
        </div>
        <a href="{{ wa_link }}" target="_blank" class="block w-full bg-green-500 hover:bg-green-600 text-white font-bold py-3 rounded-lg text-sm shadow">
            💬 Konfirmasi Pembayaran via WhatsApp
        </a>
        <a href="/pre-order" class="block text-xs text-gray-500 font-semibold hover:underline pt-2">← Buat Pesanan Baru</a>
    </div>
</body>
</html>
"""

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Panel Admin BUMDes V56</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
    <nav class="bg-white shadow-sm border-b px-6 py-4 flex justify-between items-center sticky top-0 z-50">
        <div class="flex items-center space-x-3"><span class="text-xl font-black text-orange-600">Admin POS Pro</span></div>
        <div class="flex space-x-3 text-sm">
            <a href="/admin-kebun" class="bg-emerald-600 text-white px-3 py-1.5 rounded font-bold text-xs shadow">👨‍🌾 Admin Kebun</a>
            <a href="/laporan" class="bg-purple-600 text-white px-3 py-1.5 rounded font-bold text-xs shadow">📊 Laporan Jual</a>
            <a href="/pos" class="bg-sky-600 text-white px-3 py-1.5 rounded font-bold text-xs shadow">🛒 Buka Kasir</a>
            <a href="/config-admin" class="bg-gray-800 text-white px-3 py-1.5 rounded font-bold text-xs shadow">⚙️ Setting Web</a>
            <a href="/pre-order" class="font-semibold text-gray-600 hover:text-orange-600 py-1">← Form Utama</a>
        </div>
    </nav>
    <div class="max-w-7xl mx-auto p-4 md:p-6 space-y-6">
        <h2 class="font-bold text-gray-800 text-lg mb-2">📈 Status & Rekap Data Pre-Order</h2>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-white p-4 rounded-xl shadow-sm border-l-4 border-blue-500"><div class="text-xs text-gray-500 font-semibold mb-1">Total Pesanan PO</div><div class="text-2xl font-black text-gray-800">{{ pesanan_list|length }}</div></div>
            <div class="bg-white p-4 rounded-xl shadow-sm border-l-4 border-emerald-500"><div class="text-xs text-emerald-600 font-semibold mb-1">Lunas DP</div><div class="text-2xl font-black text-emerald-700">{{ lunas_count }}</div></div>
            <div class="bg-white p-4 rounded-xl shadow-sm border-l-4 border-red-500"><div class="text-xs text-red-600 font-semibold mb-1">Menunggu DP</div><div class="text-2xl font-black text-red-700">{{ belum_count }}</div></div>
            <div class="bg-white p-4 rounded-xl shadow-sm border-l-4 border-amber-500"><div class="text-xs text-amber-600 font-semibold mb-1">Total DP Diterima</div><div class="text-xl font-black text-amber-700">Rp {{ "{:,.0f}".format(total_dp_masuk) }}</div></div>
        </div>
        <div class="bg-white rounded-2xl shadow-sm border overflow-hidden">
            <div class="p-5 border-b flex justify-between items-center bg-gray-50">
                <h2 class="font-bold text-gray-800 text-lg">📋 Tabel Detail Pesanan</h2>
                <a href="https://docs.google.com/spreadsheets/d/1nYcOD2tJ006gv9HnzSKi-tbjYLaC9nbGUuKiY02BwAI/edit" target="_blank" class="bg-emerald-600 text-white px-3 py-1.5 rounded text-xs font-bold shadow">Buka Spreadsheet ↗</a>
            </div>
            <form action="/delete-orders" method="POST" onsubmit="return confirm('Hapus permanen dari GSheets?');">
                <div class="bg-red-50 px-4 py-2 border-b flex justify-between items-center"><span class="text-xs font-semibold text-red-600">Aksi Massal:</span><button type="submit" class="bg-red-600 text-white px-3 py-1.5 rounded text-xs font-bold">🗑️ Hapus Centang</button></div>
                <div class="overflow-x-auto">
                    <table class="w-full text-left text-sm whitespace-nowrap">
                        <thead class="bg-white text-gray-600 text-xs uppercase border-b">
                            <tr><th class="p-4 w-10 text-center"><input type="checkbox" onclick="let cs=document.getElementsByName('ids_to_delete'); for(let c of cs) c.checked=this.checked;"></th><th class="p-4">ID Pesanan</th><th class="p-4">Pelanggan</th><th class="p-4">Jumlah (Butir)</th><th class="p-4">Est. Tagihan / DP</th><th class="p-4">DP Diterima</th><th class="p-4">Status DP</th><th class="p-4 text-center">Status Akhir</th></tr>
                        </thead>
                        <tbody class="divide-y divide-gray-100">
                            {% for p in pesanan_list %}
                            <tr class="hover:bg-gray-50">
                                <td class="p-4 text-center"><input type="checkbox" name="ids_to_delete" value="{{ p.id_pesanan }}"></td>
                                <td class="p-4 font-bold text-gray-800">{{ p.id_pesanan }}<br><span class="font-normal text-xs text-gray-400">{{ p.tanggal_transaksi }}</span></td>
                                <td class="p-4 font-semibold text-gray-800">{{ p.nama_pelanggan }}<br><span class="text-blue-600 font-medium text-xs">📞 {{ p.no_whatsapp }}</span></td>
                                <td class="p-4 font-bold text-gray-700">Golden: {{ p.qty_golden|int }} Btr<br>White: {{ p.qty_white|int }} Btr</td>
                                <td class="p-4 font-bold text-gray-700">Rp {{ "{:,.0f}".format(p.total_tagihan) }}<br><span class="text-[10px] text-orange-600 font-normal">DP: Rp {{ "{:,.0f}".format(p.nominal_dp) }}</span></td>
                                <td class="p-4">
                                    <div class="flex space-x-1">
                                        <input type="number" id="dp_{{ p.id_pesanan }}" value="{{ p.nominal_dp_diterima }}" class="border rounded p-1 w-24 text-right text-xs font-bold">
                                        <button type="button" onclick="simpanDP('{{ p.id_pesanan }}')" class="bg-emerald-600 text-white px-2 py-1 rounded text-xs font-bold">Save</button>
                                    </div>
                                </td>
                                <td class="p-4">
                                    {% if p.status_dp == 'Sudah' %} <span class="bg-green-100 text-green-700 px-2 py-1 rounded-full text-xs font-bold">✅ Lunas</span>
                                    {% else %} <span class="bg-red-100 text-red-700 px-2 py-1 rounded-full text-xs font-bold">⏳ Belum</span><button type="button" onclick="fastConfirm('{{ p.id_pesanan }}')" class="ml-1 bg-green-500 text-white px-2 py-1 rounded text-[10px] font-bold">Acc</button>{% endif %}
                                </td>
                                <td class="p-4 text-center">
                                    {% if p.status_pelunasan == 'Sudah Lunas' %} <span class="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-xs font-black border border-blue-300">LUNAS</span>
                                    {% else %} <span class="text-gray-400 text-xs font-semibold">Menunggu</span> {% endif %}
                                </td>
                            </tr>
                            {% endfor %}
                            {% if not pesanan_list %}
                            <tr><td colspan="8" class="p-8 text-center text-gray-400 font-bold">Belum ada data pesanan.</td></tr>
                            {% endif %}
                        </tbody>
                    </table>
                </div>
            </form>
        </div>
    </div>
    <script>
        function simpanDP(id) {
            let val = document.getElementById('dp_' + id).value, fd = new FormData(); fd.append('nominal_dp_diterima', val);
            fetch('/update-dp-diterima/' + id, { method: 'POST', body: fd }).then(() => window.location.reload());
        }
        function fastConfirm(id) { fetch('/konfirmasi-dp/' + id, { method: 'POST' }).then(() => window.location.reload()); }
    </script>
</body>
</html>
"""

# ======================= ENDPOINTS =======================

@app.get("/", response_class=HTMLResponse)
def root(): return RedirectResponse(url="/pre-order")

@app.get("/pre-order", response_class=HTMLResponse)
def pre_order_page(): return HTMLResponse(content=Template(PRE_ORDER_HTML).render(config=get_app_config()))

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    sheet = get_gspread_sheet("DataPemesan")
    pl = []
    t_dp = 0.0
    lunas_count, belum_count = 0, 0
    if sheet:
        try:
            records = sheet.get_all_values()
            if len(records) > 1:
                # Membaca data menggunakan Indeks Kolom (0, 1, 2, dst) agar tahan perubahan nama header
                for row in records[1:]:
                    if len(row) > 0 and str(row[0]).strip().startswith("PO-"):
                        dp_terima = safe_float(row[7] if len(row) > 7 else 0)
                        status_dp = str(row[8] if len(row) > 8 else "Belum").strip()
                        t_dp += dp_terima
                        if status_dp.lower() == "sudah": lunas_count += 1
                        else: belum_count += 1
                        
                        pl.append({
                            "id_pesanan": str(row[0]),
                            "tanggal_transaksi": str(row[1] if len(row)>1 else ""),
                            "nama_pelanggan": str(row[2] if len(row)>2 else ""),
                            "no_whatsapp": str(row[3] if len(row)>3 else ""),
                            "total_tagihan": safe_float(row[5] if len(row)>5 else 0),
                            "nominal_dp": safe_float(row[6] if len(row)>6 else 0),
                            "nominal_dp_diterima": dp_terima,
                            "status_dp": status_dp,
                            "qty_golden": safe_float(row[9] if len(row)>9 else 0),
                            "qty_white": safe_float(row[10] if len(row)>10 else 0),
                            "status_pelunasan": str(row[17] if len(row)>17 else "Belum")
                        })
        except Exception as e:
            print("Error Parse Admin Sheet:", e)

    return Template(ADMIN_HTML).render(
        pesanan_list=pl, config=get_app_config(), 
        total_dp_masuk=t_dp, lunas_count=lunas_count, belum_count=belum_count
    )

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
                
    url = f"/success?id={id_pes}&nama={urllib.parse.quote(nama_pelanggan)}&wa={no_whatsapp}&qg={qty_golden}&qw={qty_white}&tot={total}&dp={dp}"
    return RedirectResponse(url=url, status_code=303)

@app.get("/success", response_class=HTMLResponse)
def success_page(id: str, nama: str="", wa: str="", qg: float=0.0, qw: float=0.0, tot: float=0.0, dp: float=0.0):
    config = get_app_config()
    wa_keuangan = str(config.get("WA Admin Keuangan", "628123456790")).strip()
    if wa_keuangan.startswith('0'): wa_keuangan = '62' + wa_keuangan[1:]
    elif not wa_keuangan.startswith('62'): wa_keuangan = '62' + wa_keuangan
    
    order_dict = {
        "id_pesanan": id, "nama_pelanggan": nama, "no_whatsapp": wa,
        "qty_golden": qg, "qty_white": qw, "total_tagihan": tot, "nominal_dp": dp
    }
    
    dq = urllib.parse.quote(create_dynamic_qris(STATIC_QRIS, dp))
    pesan_wa = f"Halo Admin Keuangan, saya sudah transfer DP sebesar Rp {dp:,.0f} untuk ID Pesanan {id}."
    wa_link = f"https://api.whatsapp.com/send?phone={wa_keuangan}&text={urllib.parse.quote(pesan_wa)}"
    
    return HTMLResponse(content=Template(SUCCESS_HTML).render(order=order_dict, qris_url_encoded=dq, wa_link=wa_link))

@app.post("/update-dp-diterima/{id_pesanan}")
def update_dp_diterima(id_pesanan: str, nominal_dp_diterima: float = Form(...)):
    sheet = get_gspread_sheet("DataPemesan")
    if sheet:
        records = sheet.get_all_values()
        for i, row in enumerate(records[1:], start=2):
            if len(row) > 0 and str(row[0]).strip() == id_pesanan:
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
            if len(row) > 0 and str(row[0]).strip() == id_pesanan:
                nom_dp = safe_float(row[6]) if len(row) > 6 else 0.0
                sheet.update_cell(i, 8, nom_dp)
                sheet.update_cell(i, 9, "Sudah")
                break
    return RedirectResponse(url="/admin", status_code=303)
