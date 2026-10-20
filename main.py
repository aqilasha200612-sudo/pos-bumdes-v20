from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from datetime import datetime
import gspread
import os
import urllib.parse
from jinja2 import Template

app = FastAPI(title="POS BUMDes Kembaran Versi 55 (Full GSheets & UI Restored)")

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
        print("ERROR: credentials.json tidak ada di Vercel!")
        return None
    try:
        client = gspread.service_account(filename="credentials.json")
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        try: return spreadsheet.worksheet(sheet_name)
        except Exception:
            if sheet_name == "Config":
                sheet = spreadsheet.add_worksheet(title="Config", rows=10, cols=10)
                sheet.append_row(["Kuota Promo", "Persen Diskon", "Tanggal Panen", "WA Admin Utama", "WA Admin Keuangan", "WA Admin Kebun", "Harga Per Kg"])
                sheet.append_row([100, 10, "2026-11-15", "628123456789", "628123456790", "628123456791", 52500])
                return sheet
            elif sheet_name == "POS":
                sheet = spreadsheet.add_worksheet(title="POS", rows=100, cols=12)
                sheet.append_row(["ID POS", "Tanggal", "Tipe Transaksi", "ID Referensi PO", "Nama Pelanggan", "Qty Golden", "Qty White", "Diskon", "Total Tagihan", "Dibayar", "Kembalian", "Metode Pembayaran"])
                return sheet
            elif sheet_name == "Aktual_Kebun":
                sheet = spreadsheet.add_worksheet(title="Aktual_Kebun", rows=100, cols=10)
                sheet.append_row(["ID Pesanan", "Waktu Timbang", "Nama Pelanggan", "Lajur Golden", "Baris Golden", "Aktual Golden (KG)", "Lajur White", "Baris White", "Aktual White (KG)"])
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
        print("ERROR GSPREAD:", e)
        return None

def get_app_config():
    sheet = get_gspread_sheet("Config")
    if sheet:
        try:
            records = sheet.get_all_values()
            if len(records) > 1:
                headers = [str(h).strip() for h in records[0]]
                row = records[1]
                row_padded = row + [""] * (len(headers) - len(row))
                conf = dict(zip(headers, row_padded))
                try: conf['Harga Per Kg'] = safe_float(conf.get('Harga Per Kg', '52500'))
                except: conf['Harga Per Kg'] = 52500.0
                return conf
        except Exception: pass
    return {"Kuota Promo": 100, "Persen Diskon": 0.0, "Tanggal Panen": "Segera", "WA Admin Utama": "628123456789", "WA Admin Keuangan": "628123456790", "WA Admin Kebun": "628123456791", "Harga Per Kg": 52500.0}

# ======================= HTML TEMPLATES (FULL VERSION) =======================

ADMIN_KEBUN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Panel Admin Kebun BUMDes V53</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config = { theme: { extend: { colors: { pos: '#059669' } } } }</script>
</head>
<body class="bg-emerald-50 min-h-screen pb-10">
    <nav class="bg-emerald-700 shadow-md px-6 py-4 flex justify-between items-center sticky top-0 z-50 text-white">
        <div class="flex items-center space-x-3"><span class="text-2xl">👨‍🌾</span><span class="text-xl font-black tracking-wide">PANEL ADMIN KEBUN</span></div>
        <div class="flex space-x-3 text-sm">
            <a href="/admin" class="bg-white text-emerald-800 px-3 py-1.5 rounded font-bold text-xs shadow hover:bg-gray-100 transition">← Admin Pusat</a>
            <a href="/pos" class="bg-blue-600 text-white px-3 py-1.5 rounded font-bold text-xs shadow hover:bg-blue-700 transition">🛒 Ke Kasir</a>
        </div>
    </nav>
    <div class="max-w-7xl mx-auto p-4 space-y-6 mt-4">
        <div class="bg-white rounded-2xl shadow-sm border border-emerald-200 overflow-hidden">
            <div class="p-4 bg-emerald-600 text-white flex justify-between items-center"><h2 class="font-bold text-lg">➕ Input Stok Buah Tersedia di Kebun</h2></div>
            <div class="p-5 bg-emerald-50/50">
                <form action="/input-stok" method="POST" class="flex flex-col md:flex-row gap-4 items-end">
                    <div class="w-full md:w-1/5"><label class="text-xs font-bold text-gray-700 block mb-1">Lajur</label><select name="lajur" class="w-full border rounded p-2 text-sm font-bold bg-white" required>{% for l in ['A','B','C','D','E','F','G'] %}<option value="{{l}}">Lajur {{l}}</option>{% endfor %}</select></div>
                    <div class="w-full md:w-1/5"><label class="text-xs font-bold text-gray-700 block mb-1">Baris</label><select name="baris" class="w-full border rounded p-2 text-sm font-bold bg-white" required>{% for b in range(1, 11) %}<option value="{{b}}">Baris {{b}}</option>{% endfor %}</select></div>
                    <div class="w-full md:w-1/5"><label class="text-xs font-bold text-gray-700 block mb-1">Jenis Buah</label><select name="jenis_buah" class="w-full border rounded p-2 text-sm font-bold bg-white" required><option value="Golden">Melon Golden</option><option value="White">Melon White</option></select></div>
                    <div class="w-full md:w-1/5"><label class="text-xs font-bold text-gray-700 block mb-1">Berat Aktual (KG)</label><input type="number" step="any" name="berat" value="" placeholder="Contoh: 1.5" class="w-full border rounded p-2 text-sm font-black bg-white" required></div>
                    <div class="w-full md:w-1/5"><button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-2 px-4 rounded text-sm shadow">💾 Simpan ke Denah</button></div>
                </form>
            </div>
        </div>
        <div class="bg-white rounded-2xl shadow-sm border border-emerald-200 overflow-hidden">
            <div class="p-4 border-b bg-gray-50 flex justify-between items-center"><h2 class="font-bold text-gray-800 text-lg">🗺️ Denah Lokasi & Status Stok Aktual</h2></div>
            <div class="p-4 overflow-x-auto bg-emerald-50/50">
                <div class="min-w-[800px]">
                    <div class="grid grid-cols-8 gap-2 text-center text-xs mb-2"><div></div>{% for l in ['A','B','C','D','E','F','G'] %}<div class="font-black bg-emerald-200 text-emerald-800 py-2 rounded shadow-sm">LAJUR {{ l }}</div>{% endfor %}</div>
                    {% for baris in range(1, 11) %}
                    <div class="grid grid-cols-8 gap-2 mt-2">
                        <div class="font-black bg-emerald-100 text-emerald-800 flex items-center justify-center rounded shadow-sm">BARIS {{ baris }}</div>
                        {% for lajur in ['A','B','C','D','E','F','G'] %}
                        <div class="border border-emerald-200 rounded p-1 min-h-[55px] bg-white text-[10px] text-left shadow-sm relative">
                            {% if denah[lajur][baris]|length > 0 %}
                                {% for item in denah[lajur][baris] %}
                                    <div class="{% if item.status == 'Tersedia' %}bg-green-100 text-green-800 border-green-300{% else %}bg-yellow-100 text-yellow-800 border-yellow-300{% endif %} font-bold mb-1 px-1.5 py-1 rounded border leading-tight">
                                        <div class="flex justify-between"><span>{{ 'G' if item.jenis == 'Golden' else 'W' }}: {{ item.berat }}kg</span><a href="/hapus-stok/{{ item.id }}" onclick="return confirm('Hapus stok ini?')" class="text-red-500">✕</a></div>
                                        {% if item.status != 'Tersedia' %}<div class="text-[8px] mt-0.5 text-gray-600 truncate border-t border-yellow-200 pt-0.5">PO: {{ item.pemesan }}</div>{% endif %}
                                    </div>
                                {% endfor %}
                            {% else %}<div class="text-gray-300 text-center italic mt-3 text-[9px]">Kosong</div>{% endif %}
                        </div>
                        {% endfor %}
                    </div>
                    {% endfor %}
                </div>
            </div>
        </div>
        <div class="bg-white rounded-2xl shadow-sm border border-emerald-200 overflow-hidden">
            <div class="p-4 border-b bg-gray-50 flex justify-between items-center"><h2 class="font-bold text-gray-800 text-lg">📋 Plotting Pesanan PO ke Denah Kebun</h2></div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm whitespace-nowrap">
                    <thead class="bg-emerald-600 text-white text-[11px] uppercase border-b">
                        <tr><th class="p-4 w-1/4">Info Pelanggan & PO</th><th class="p-4 bg-orange-600/90 w-1/4">🍈 Pilih Stok Golden</th><th class="p-4 bg-teal-600/90 w-1/4">🍈 Pilih Stok White</th><th class="p-4 text-center w-1/4">Aksi / Kirim WA</th></tr>
                    </thead>
                    <tbody class="divide-y divide-gray-200">
                        {% for p in pesanan_list %}
                        <tr class="hover:bg-emerald-50 transition">
                            <td class="p-4"><div class="font-bold text-gray-800 text-base">{{ p.nama_pelanggan }}</div><div class="font-mono text-xs text-gray-500">{{ p.id_pesanan }}</div><div class="text-[11px] text-blue-600 mt-1 font-semibold">📞 {{ p.no_whatsapp }}</div></td>
                            <td class="p-4 bg-orange-50/30 align-top">
                                {% if p.qty_golden > 0 %}
                                    <select id="sg_{{ p.id_pesanan }}" class="w-full border rounded p-1.5 text-xs font-bold bg-white"><option value="">-- Pilih Stok Golden --</option>
                                    {% for s in stok_g %}{% if s.status == 'Tersedia' or s.id_pesanan == p.id_pesanan %}<option value="{{s.id}}" {% if s.id_pesanan == p.id_pesanan %}selected{% endif %}>Lajur {{s.lajur}} - Brs {{s.baris}} ({{s.berat}} KG)</option>{% endif %}{% endfor %}
                                    </select>
                                {% else %}<div class="text-xs text-gray-400 italic">Tidak beli Golden</div>{% endif %}
                            </td>
                            <td class="p-4 bg-teal-50/30 align-top">
                                {% if p.qty_white > 0 %}
                                    <select id="sw_{{ p.id_pesanan }}" class="w-full border rounded p-1.5 text-xs font-bold bg-white"><option value="">-- Pilih Stok White --</option>
                                    {% for s in stok_w %}{% if s.status == 'Tersedia' or s.id_pesanan == p.id_pesanan %}<option value="{{s.id}}" {% if s.id_pesanan == p.id_pesanan %}selected{% endif %}>Lajur {{s.lajur}} - Brs {{s.baris}} ({{s.berat}} KG)</option>{% endif %}{% endfor %}
                                    </select>
                                {% else %}<div class="text-xs text-gray-400 italic">Tidak beli White</div>{% endif %}
                            </td>
                            <td class="p-4 text-center space-y-2 align-top">
                                <button type="button" onclick="simpanPlotting('{{ p.id_pesanan }}')" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white px-3 py-2 rounded text-xs font-bold shadow">💾 Tandai Denah & Simpan</button>
                                <button type="button" onclick="kirimWA('{{ p.id_pesanan }}', '{{ p.nama_pelanggan }}', '{{ p.no_whatsapp }}', {{ p.qty_golden }}, {{ p.qty_white }})" class="w-full bg-green-500 hover:bg-green-600 text-white px-3 py-2 rounded text-xs font-bold shadow">📱 Kirim WA</button>
                            </td>
                        </tr>
                        {% endfor %}
                        {% if not pesanan_list %}<tr><td colspan="4" class="p-8 text-center text-gray-400 font-bold">Belum ada pesanan PO yang aktif.</td></tr>{% endif %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script>
        async function simpanPlotting(id) {
            let sg = document.getElementById('sg_'+id)?.value || ''; 
            let sw = document.getElementById('sw_'+id)?.value || '';
            let fd = new FormData(); fd.append('id_sg', sg); fd.append('id_sw', sw);
            try {
                let res = await fetch('/update-kebun/' + id, { method: 'POST', body: fd });
                if(res.ok) { alert("Plotting berhasil!"); window.location.reload(); }
                else alert("Gagal menyimpan data!");
            } catch(e) { alert("Error jaringan."); }
        }
        function kirimWA(id, nama, hp, qtyG, qtyW) {
            let elG = document.getElementById('sg_'+id);
            let elW = document.getElementById('sw_'+id);
            let txtG = (qtyG > 0 && elG && elG.value) ? elG.options[elG.selectedIndex].text : "Belum diplot";
            let txtW = (qtyW > 0 && elW && elW.value) ? elW.options[elW.selectedIndex].text : "Belum diplot";
            let no = hp.trim(); if(no.startsWith('0')) no = '62' + no.substring(1);
            let pesan = `Halo Bpk/Ibu *${nama}*,\n\nPesanan (ID: *${id}*) sudah siap di kebun:\n`;
            if(qtyG > 0) pesan += `- Golden: ${txtG}\n`;
            if(qtyW > 0) pesan += `- White: ${txtW}\n`;
            pesan += `\nSilakan tunjukkan pesan ini ke kasir. Terima kasih.`;
            window.open(`https://api.whatsapp.com/send?phone=${no}&text=` + encodeURIComponent(pesan), '_blank');
        }
    </script>
</body>
</html>
"""

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
        <button type="button" onclick="cetakStrukPO()" class="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-2.5 rounded-lg text-xs shadow">
            🖨️ Cetak Bukti Pre-Order (Thermal)
        </button>
        <a href="/pre-order" class="block text-xs text-gray-500 font-semibold hover:underline pt-2">← Buat Pesanan Baru</a>
    </div>

    <!-- Hidden Printable Area for Thermal Struk PO -->
    <div id="print_area" class="hidden">
        <div style="font-family: monospace; width: 280px; padding: 10px; font-size: 12px; line-height: 1.2;">
            <div style="text-align: center; font-weight: bold; font-size: 14px;">BUMDES KEMBARAN</div>
            <div style="text-align: center; font-size: 10px;">BUKTI PRE-ORDER MELON</div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 5px 0;"></div>
            <div>ID PO  : {{ order.id_pesanan }}</div>
            <div>Tgl    : {{ order.tanggal_transaksi }}</div>
            <div>Nama   : {{ order.nama_pelanggan }}</div>
            <div>Telp   : {{ order.no_whatsapp }}</div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 5px 0;"></div>
            <div>Rincian Pesanan:</div>
            {% if order.qty_golden > 0 %}
            <div>- Melon Golden : {{ order.qty_golden|int }} Btr</div>
            {% endif %}
            {% if order.qty_white > 0 %}
            <div>- Melon White  : {{ order.qty_white|int }} Btr</div>
            {% endif %}
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 5px 0;"></div>
            <div>Est. Tagihan : Rp {{ "{:,.0f}".format(order.total_tagihan) }}</div>
            <div style="font-weight: bold;">DP WAJIB (50%): Rp {{ "{:,.0f}".format(order.nominal_dp) }}</div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 5px 0;"></div>
            <div style="text-align: center; font-size: 10px;">Mohon transfer DP via QRIS & konfirmasi WA.<br>Terima Kasih!</div>
        </div>
    </div>
    <script>
        function cetakStrukPO() {
            let content = document.getElementById('print_area').innerHTML;
            let win = window.open('', '', 'height=600,width=400');
            win.document.write('<html><head><title>Cetak PO</title></head><body>');
            win.document.write(content);
            win.document.write('</body></html>');
            win.document.close();
            win.focus();
            setTimeout(() => { win.print(); win.close(); }, 300);
        }
    </script>
</body>
</html>
"""

POS_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Kasir POS BUMDes Kembaran</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>tailwind.config = { theme: { extend: { colors: { pos: '#0284c7', poshigh: '#0369a1' } } } }</script>
</head>
<body class="bg-gray-100 min-h-screen">
    <nav class="bg-white shadow-sm border-b px-6 py-4 flex justify-between items-center sticky top-0 z-50">
        <div class="flex items-center space-x-3"><span class="text-2xl">🛒</span><span class="text-xl font-black text-pos">KASIR POS</span></div>
        <div class="flex space-x-3 text-sm items-center">
            <a href="/admin-kebun" class="bg-emerald-600 text-white px-3 py-1.5 rounded font-bold text-xs shadow hover:bg-emerald-700">👨‍🌾 Kebun</a>
            <button type="button" id="btnReprint" onclick="cetakUlangStruk()" class="bg-orange-500 hover:bg-orange-600 text-white font-bold px-3 py-1.5 rounded text-xs shadow hidden">🖨️ Cetak Struk Terakhir</button>
            <button type="button" onclick="bukaModalPrinter()" class="bg-teal-600 hover:bg-teal-700 text-white font-bold px-3 py-1.5 rounded text-xs shadow">🖨️ Setting Printer</button>
            <a href="/admin" class="font-semibold text-gray-600 hover:text-pos py-1">← Admin</a>
        </div>
    </nav>
    <div class="max-w-5xl mx-auto p-4 md:p-6 mt-4">
        <div id="alert_area"></div>
        <div class="bg-white rounded-2xl shadow-md border overflow-hidden flex flex-col md:flex-row">
            <div class="w-full md:w-1/2 p-6 border-r bg-gray-50">
                <h2 class="font-bold text-gray-800 text-lg mb-4">Pilih Mode Transaksi</h2>
                <div class="flex space-x-4 mb-6">
                    <label class="flex items-center space-x-2 cursor-pointer"><input type="radio" name="mode" value="Langsung" checked onclick="switchMode('Langsung')" class="w-4 h-4 text-pos"><span class="font-semibold text-sm text-gray-700">Penjualan Langsung</span></label>
                    <label class="flex items-center space-x-2 cursor-pointer"><input type="radio" name="mode" value="Pelunasan PO" onclick="switchMode('PO')" class="w-4 h-4 text-pos"><span class="font-semibold text-sm text-gray-700">Pelunasan Pre-Order</span></label>
                </div>
                <div id="mode_po" class="space-y-4" style="display: none;">
                    <div class="bg-blue-50 p-4 rounded-xl border border-blue-100 shadow-sm relative">
                        <label class="text-xs font-bold text-blue-800 block mb-2">Cari Nama Pelanggan / ID PO</label>
                        <div class="flex space-x-2">
                            <input type="text" id="search_po_id" placeholder="Ketik Nama..." onkeyup="onKetikCari(event)" autocomplete="off" class="w-full p-2.5 border rounded text-sm shadow-sm">
                            <button type="button" onclick="cariPO()" class="bg-blue-600 text-white px-5 py-2.5 rounded font-bold text-sm shadow">Cari</button>
                        </div>
                        <div id="dropdown_po_list" class="absolute left-4 right-4 bg-white border border-gray-300 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto z-50 hidden"></div>
                        <p id="po_status_msg" class="text-xs mt-3 font-semibold"></p>
                    </div>
                    <div id="area_berat_aktual" class="space-y-4 hidden bg-emerald-50 p-4 rounded-xl border border-emerald-200 shadow-sm">
                        <h3 class="font-bold text-emerald-800 text-xs uppercase">⚖️ Data Berat Aktual (Sinkron Kebun)</h3>
                        <div class="grid grid-cols-2 gap-3">
                            <div class="bg-white p-3 rounded-lg border"><label class="text-[10px] font-bold text-gray-600 block text-center">Aktual Golden (KG)</label><input type="text" id="input_aktual_golden" value="0" onkeyup="hitungTotalKasir()" class="w-full border rounded p-1.5 text-lg font-black text-center text-gray-800"></div>
                            <div class="bg-white p-3 rounded-lg border"><label class="text-[10px] font-bold text-gray-600 block text-center">Aktual White (KG)</label><input type="text" id="input_aktual_white" value="0" onkeyup="hitungTotalKasir()" class="w-full border rounded p-1.5 text-lg font-black text-center text-gray-800"></div>
                        </div>
                    </div>
                </div>
                <div id="mode_langsung" class="space-y-4">
                    <div class="bg-white p-4 rounded-xl border shadow-sm"><label class="text-xs font-bold text-gray-700 block mb-2">Nama Pelanggan (Walk-in)</label><input type="text" id="input_nama" onkeyup="hitungTotalKasir()" placeholder="Contoh: Bpk. Budi" class="w-full p-2.5 border rounded text-sm shadow-sm"></div>
                    <div class="grid grid-cols-2 gap-4">
                        <div class="border rounded-lg shadow-sm p-3 relative bg-white flex flex-col justify-between">
                            <div class="absolute top-0 left-0 bg-red-500 text-white text-[10px] px-2 py-0.5 rounded-br-lg font-bold">Golden Humi</div>
                            <div class="mt-5 flex justify-center"><img src="https://lh3.googleusercontent.com/d/1E7kjiNX0RfAHoysDqtyce-WiKWM72KMn" class="h-20 w-20 object-cover rounded-md mb-2"></div>
                            <div class="text-center"><h2 class="text-xs font-bold text-gray-800">Melon Golden</h2></div>
                            <div class="mt-2"><label class="text-[10px] font-bold text-gray-500 block text-center">Berat (KG)</label><input type="text" id="input_golden" value="0" onkeyup="hitungTotalKasir()" class="w-full border rounded p-1.5 text-lg font-black text-center"></div>
                        </div>
                        <div class="border rounded-lg shadow-sm p-3 relative bg-white flex flex-col justify-between">
                            <div class="absolute top-0 left-0 bg-emerald-500 text-white text-[10px] px-2 py-0.5 rounded-br-lg font-bold">White Humi</div>
                            <div class="mt-5 flex justify-center"><img src="https://lh3.googleusercontent.com/d/1MYZFh0OqnNjPE113wQWONrbxhpoEIwtm" class="h-20 w-20 object-cover rounded-md mb-2"></div>
                            <div class="text-center"><h2 class="text-xs font-bold text-gray-800">Melon White</h2></div>
                            <div class="mt-2"><label class="text-[10px] font-bold text-gray-500 block text-center">Berat (KG)</label><input type="text" id="input_white" value="0" onkeyup="hitungTotalKasir()" class="w-full border rounded p-1.5 text-lg font-black text-center"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="w-full md:w-1/2 p-6 flex flex-col justify-between bg-white">
                <div>
                    <h2 class="font-bold text-gray-800 text-lg mb-4 border-b pb-2">Ringkasan Tagihan</h2>
                    <div class="bg-gray-50 rounded-lg p-4 mb-4 border"><div class="space-y-3 text-sm text-gray-600">
                        <div class="flex justify-between border-b pb-2"><span>Pelanggan:</span><span id="sum_nama" class="font-bold text-gray-800">Pelanggan Umum</span></div>
                        <div class="flex justify-between border-b pb-2"><span>Rincian:</span><span id="sum_qty" class="font-bold text-gray-800">0 Butir (0 KG)</span></div>
                        <div id="row_subtotal" class="flex justify-between text-gray-500 pb-2 border-b"><span>Subtotal:</span><span id="sum_subtotal" class="font-semibold">Rp 0</span></div>
                        <div id="row_total_awal" class="flex justify-between hidden text-gray-500 pb-2 border-b"><span>Total Tagihan Aktual:</span><span id="sum_total_awal" class="font-semibold">Rp 0</span></div>
                        <div id="row_dp" class="flex justify-between hidden text-emerald-600 pb-2 border-b"><span>Telah Dibayar (DP):</span><span id="sum_dp" class="font-bold">- Rp 0</span></div>
                    </div></div>
                    <div class="bg-orange-50 border border-orange-200 p-3 rounded-xl mb-4">
                        <label class="text-xs font-bold text-orange-800 block mb-2">🎁 Diskon / Potongan Kasir</label>
                        <div class="grid grid-cols-2 gap-2">
                            <select id="input_diskon_tipe" onchange="hitungTotalKasir()" class="w-full border rounded p-2 text-xs font-bold bg-white"><option value="persen">Persen (%)</option><option value="nominal">Nominal (Rp)</option></select>
                            <input type="number" id="input_diskon_nilai" value="0" min="0" onkeyup="hitungTotalKasir()" placeholder="Nilai Diskon" class="w-full border rounded p-2 text-xs font-bold bg-white text-right">
                        </div>
                    </div>
                    <div class="bg-blue-50 border-2 border-blue-100 p-5 rounded-xl text-center mb-6">
                        <div class="text-xs font-bold text-blue-600 uppercase mb-2" id="label_tagihan">TOTAL YANG HARUS DIBAYAR</div>
                        <div class="text-4xl font-black text-pos" id="tampil_tagihan">Rp 0</div>
                    </div>
                    <div class="mb-4">
                        <label class="text-xs font-bold text-gray-700 block mb-2">Metode Pembayaran</label>
                        <div class="flex space-x-4">
                            <label class="flex items-center space-x-2 cursor-pointer bg-gray-50 p-3 border rounded-lg w-1/2 justify-center"><input type="radio" name="metode" value="Tunai" checked onclick="pilihMetode('Tunai')" class="text-pos"><span class="font-bold text-sm">💵 Tunai</span></label>
                            <label class="flex items-center space-x-2 cursor-pointer bg-gray-50 p-3 border rounded-lg w-1/2 justify-center"><input type="radio" name="metode" value="QRIS" onclick="pilihMetode('QRIS')" class="text-pos"><span class="font-bold text-sm">📱 QRIS</span></label>
                        </div>
                    </div>
                    <div id="area_tunai" class="space-y-3">
                        <label class="text-xs font-bold text-gray-700 block">Uang Diterima (Tunai)</label>
                        <div class="relative"><span class="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-500 font-bold">Rp</span><input type="number" id="input_bayar" value="0" onkeyup="hitungKembalian()" class="w-full border-2 border-gray-300 rounded-lg p-4 pl-12 text-3xl font-black text-right bg-gray-50"></div>
                        <div class="flex justify-between items-center mt-4 p-4 bg-red-50 rounded-xl border border-red-200"><span class="text-sm font-bold text-red-800">KEMBALIAN:</span><span class="text-2xl font-black text-red-700" id="tampil_kembali">Rp 0</span></div>
                    </div>
                    <div id="area_qris" class="hidden text-center mt-2">
                        <div class="bg-white p-4 rounded-xl border-2 border-blue-500 inline-block relative w-full">
                            <div class="absolute -top-3 left-1/2 transform -translate-x-1/2 bg-blue-500 text-white text-xs font-bold px-3 py-1 rounded-full">SCAN QRIS PELANGGAN</div>
                            <img id="img_qris" src="" class="h-48 w-48 object-contain mx-auto mt-2">
                            <p class="text-sm text-gray-600 mt-3 font-semibold">Bayar: <span id="label_qris_bayar" class="text-blue-700 font-black text-lg">Rp 0</span></p>
                        </div>
                    </div>
                </div>
                <form id="form_pos" class="mt-8" onsubmit="prosesTransaksi(event)">
                    <input type="hidden" name="tipe_transaksi" id="post_tipe" value="Langsung">
                    <input type="hidden" name="id_po" id="post_id_po" value="">
                    <input type="hidden" name="nama_pelanggan" id="post_nama" value="Pelanggan Umum">
                    <input type="hidden" name="qty_golden" id="post_qty_golden" value="0">
                    <input type="hidden" name="qty_white" id="post_qty_white" value="0">
                    <input type="hidden" name="diskon_keterangan" id="post_diskon_ket" value="-">
                    <input type="hidden" name="tagihan_aktif" id="post_tagihan" value="0">
                    <input type="hidden" name="nominal_bayar" id="post_bayar" value="0">
                    <input type="hidden" name="metode_pembayaran" id="post_metode" value="Tunai">
                    <button type="submit" id="btnSimpan" class="w-full bg-pos hover:bg-poshigh text-white font-black text-lg py-4 rounded-xl shadow-lg">SIMPAN & CETAK STRUK 🖨️</button>
                </form>
            </div>
        </div>
    </div>

    <!-- Hidden Printable Receipt Template -->
    <div id="receipt_container" class="hidden">
        <div style="font-family: monospace; width: 280px; padding: 10px; font-size: 12px; line-height: 1.2; color: #000;" id="receipt_content_inner">
            <div style="text-align: center; font-weight: bold; font-size: 15px;">BUMDES KEMBARAN</div>
            <div style="text-align: center; font-size: 11px;">Pusat Buah Melon Berkualitas</div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 6px 0;"></div>
            <div id="rc_id">ID : TRX-000000</div>
            <div id="rc_tgl">Tgl: 2026-10-18 14:30</div>
            <div id="rc_nama">Plg: Pelanggan Umum</div>
            <div id="rc_tipe">Tipe: Penjualan Langsung</div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 6px 0;"></div>
            <div id="rc_rincian">Rincian Barang</div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 6px 0;"></div>
            <div style="display: flex; justify-content: space-between;"><span>Subtotal:</span><span id="rc_sub">Rp 0</span></div>
            <div style="display: flex; justify-content: space-between;"><span>Diskon:</span><span id="rc_disk">-</span></div>
            <div style="display: flex; justify-content: space-between; font-weight: bold; font-size: 13px;"><span>TOTAL:</span><span id="rc_tot">Rp 0</span></div>
            <div style="display: flex; justify-content: space-between;"><span>Bayar (<span id="rc_metode">Tunai</span>):</span><span id="rc_bayar">Rp 0</span></div>
            <div style="display: flex; justify-content: space-between;" id="row_rc_kembali"><span>Kembalian:</span><span id="rc_kembali">Rp 0</span></div>
            <div style="text-align: center; border-bottom: 1px dashed #000; margin: 6px 0;"></div>
            <div style="text-align: center; font-size: 10px;">Terima Kasih Atas Kunjungan Anda<br>Barang yang sudah dibeli tidak dapat ditukar</div>
        </div>
    </div>

    <!-- Modal Setting Printer -->
    <div id="modal_printer" class="fixed inset-0 bg-black bg-opacity-50 z-[100] flex items-center justify-center hidden">
        <div class="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl space-y-5">
            <div class="flex justify-between items-center border-b pb-3"><h3 class="font-bold text-gray-800 text-lg">🖨️ Pengaturan Printer & Ukuran Kertas</h3><button type="button" onclick="tutupModalPrinter()" class="text-gray-400 font-bold text-lg">✕</button></div>
            <div class="space-y-4 text-sm">
                <div class="bg-gray-50 p-4 rounded-xl border"><label class="font-bold text-gray-700 block text-xs mb-2">Pilih Metode Cetak & Kertas</label>
                    <div class="space-y-2">
                        <label class="flex items-center space-x-2 bg-white p-2.5 border rounded-lg cursor-pointer"><input type="radio" name="print_method" value="browser" checked class="text-pos"><span>🖨️ Dialog Print Browser (Rekomendasi / USB / PDF / Printer Windows)</span></label>
                        <label class="flex items-center space-x-2 bg-white p-2.5 border rounded-lg cursor-pointer"><input type="radio" name="print_method" value="bluetooth" class="text-pos"><span>📶 Bluetooth Thermal Printer (Android / PC Web Bluetooth)</span></label>
                    </div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div class="border p-4 rounded-xl bg-gray-50"><div class="font-bold text-gray-700 flex justify-between text-xs mb-2"><span>Bluetooth</span><span id="status_bt" class="text-[10px] px-2 py-0.5 rounded bg-red-100 text-red-700 font-bold">Terputus</span></div><button type="button" onclick="pairBluetoothPrinter()" class="w-full bg-blue-600 text-white font-bold py-2 rounded text-xs mb-1">🔗 Hubungkan BT</button><button type="button" id="btn_disconnect_bt" onclick="lupakanPrinter()" class="w-full bg-red-100 text-red-700 font-bold py-1 rounded text-[10px] hidden">✕ Putus</button></div>
                    <div class="border p-4 rounded-xl bg-gray-50"><div class="font-bold text-gray-700 flex justify-between text-xs mb-2"><span>Test Cetak</span><span class="text-[10px] px-2 py-0.5 rounded bg-green-100 text-green-700 font-bold">Ready</span></div><button type="button" onclick="cetakStrukContoh()" class="w-full bg-yellow-600 text-white font-bold py-2.5 rounded text-xs mt-2">🖨️ Test Print Struk</button></div>
                </div>
            </div>
            <div class="flex justify-end pt-2"><button type="button" onclick="tutupModalPrinter()" class="bg-gray-200 px-4 py-2 rounded text-xs font-bold">Tutup</button></div>
        </div>
    </div>

    <script>
        const HARGA_PER_KG = {{ config.get('Harga Per Kg', 52500.0) }};
        let modeAktif = 'Langsung', metodeAktif = 'Tunai', tagihanAktif = 0, subtotalGlobal = 0, objPO = null;
        let bluetoothDevice = null, printCharacteristic = null, lastTransactionData = null;

        function switchMode(mode) {
            let elPo = document.getElementById('mode_po'), elLangsung = document.getElementById('mode_langsung'), elBeratAktual = document.getElementById('area_berat_aktual');
            if(mode === 'PO') {
                modeAktif = 'Pelunasan PO'; document.getElementById('post_tipe').value = modeAktif;
                elLangsung.style.display = 'none'; elPo.style.display = 'block'; elBeratAktual.classList.remove('hidden');
                document.getElementById('row_dp').classList.remove('hidden'); document.getElementById('row_total_awal').classList.remove('hidden'); document.getElementById('row_subtotal').classList.add('hidden');
                document.getElementById('label_tagihan').innerText = "SISA TAGIHAN (PELUNASAN)"; resetHitungan(); setTimeout(() => document.getElementById('search_po_id').focus(), 100);
            } else {
                modeAktif = 'Langsung'; document.getElementById('post_tipe').value = modeAktif;
                elPo.style.display = 'none'; elBeratAktual.classList.add('hidden'); elLangsung.style.display = 'block';
                document.getElementById('row_dp').classList.add('hidden'); document.getElementById('row_total_awal').classList.add('hidden'); document.getElementById('row_subtotal').classList.remove('hidden');
                document.getElementById('label_tagihan').innerText = "TOTAL YANG HARUS DIBAYAR"; objPO = null; hitungTotalKasir();
            }
        }
        function pilihMetode(metode) { metodeAktif = metode; document.getElementById('post_metode').value = metodeAktif; updatePaymentUI(); }
        function updatePaymentUI() {
            if(metodeAktif === 'QRIS') {
                document.getElementById('area_tunai').classList.add('hidden'); document.getElementById('area_qris').classList.remove('hidden');
                document.getElementById('input_bayar').value = tagihanAktif; document.getElementById('post_bayar').value = tagihanAktif;
                if (tagihanAktif > 0) fetch('/api/qris?amount=' + tagihanAktif).then(r => r.json()).then(data => { document.getElementById('img_qris').src = data.qris_url; document.getElementById('label_qris_bayar').innerText = "Rp " + tagihanAktif.toLocaleString('id-ID'); });
            } else { document.getElementById('area_qris').classList.add('hidden'); document.getElementById('area_tunai').classList.remove('hidden'); hitungKembalian(); }
        }
        function resetHitungan() {
            tagihanAktif = 0; subtotalGlobal = 0; document.getElementById('tampil_tagihan').innerText = "Rp 0";
            document.getElementById('sum_nama').innerText = "-"; document.getElementById('sum_qty').innerText = "0 Butir (0 KG)";
            document.getElementById('sum_subtotal').innerText = "Rp 0"; document.getElementById('sum_total_awal').innerText = "Rp 0"; document.getElementById('sum_dp').innerText = "- Rp 0";
            document.getElementById('input_diskon_nilai').value = "0"; document.getElementById('input_bayar').value = ""; document.getElementById('tampil_kembali').innerText = "Rp 0"; updatePaymentUI();
        }
        function parseQtyInput(id) { return parseFloat((document.getElementById(id).value || "0").replace(',', '.')) || 0; }
        function hitungTotalKasir() {
            let diskonTipe = document.getElementById('input_diskon_tipe').value, diskonNilai = parseFloat(document.getElementById('input_diskon_nilai').value) || 0, diskonKetStr = "-";
            if (modeAktif === 'Langsung') {
                let qtyG = parseQtyInput('input_golden'), qtyW = parseQtyInput('input_white'), nama = document.getElementById('input_nama').value || "Pelanggan Umum";
                subtotalGlobal = (qtyG + qtyW) * HARGA_PER_KG; let potongan = 0;
                if (diskonNilai > 0) { potongan = diskonTipe === 'persen' ? subtotalGlobal * (diskonNilai / 100) : diskonNilai; diskonKetStr = `${diskonNilai}${diskonTipe === 'persen' ? '%' : ' Rp'} (Rp ${potongan.toLocaleString('id-ID')})`; }
                tagihanAktif = Math.max(0, subtotalGlobal - potongan);
                document.getElementById('sum_nama').innerText = nama; document.getElementById('sum_qty').innerText = "Langsung (" + qtyG.toFixed(1) + " / " + qtyW.toFixed(1) + " KG)";
                document.getElementById('sum_subtotal').innerText = "Rp " + subtotalGlobal.toLocaleString('id-ID'); document.getElementById('tampil_tagihan').innerText = "Rp " + tagihanAktif.toLocaleString('id-ID');
                document.getElementById('post_nama').value = nama; document.getElementById('post_qty_golden').value = qtyG; document.getElementById('post_qty_white').value = qtyW; document.getElementById('post_diskon_ket').value = diskonKetStr; document.getElementById('post_tagihan').value = tagihanAktif;
            } else if (modeAktif === 'Pelunasan PO' && objPO) {
                let aktG = parseQtyInput('input_aktual_golden'), aktW = parseQtyInput('input_aktual_white');
                subtotalGlobal = (aktG + aktW) * HARGA_PER_KG; let potongan = 0;
                if (diskonNilai > 0) { potongan = diskonTipe === 'persen' ? subtotalGlobal * (diskonNilai / 100) : diskonNilai; diskonKetStr = `${diskonNilai}${diskonTipe === 'persen' ? '%' : ' Rp'} (Rp ${potongan.toLocaleString('id-ID')})`; }
                let totalAktifTagihan = subtotalGlobal - potongan; tagihanAktif = Math.max(0, totalAktifTagihan - objPO.dp_diterima);
                document.getElementById('sum_qty').innerText = `${objPO.qty_golden} Btr (G: ${aktG.toFixed(1)}kg) | ${objPO.qty_white} Btr (W: ${aktW.toFixed(1)}kg)`;
                document.getElementById('sum_total_awal').innerText = "Rp " + totalAktifTagihan.toLocaleString('id-ID'); document.getElementById('tampil_tagihan').innerText = "Rp " + tagihanAktif.toLocaleString('id-ID');
                document.getElementById('post_qty_golden').value = aktG; document.getElementById('post_qty_white').value = aktW; document.getElementById('post_diskon_ket').value = diskonKetStr; document.getElementById('post_tagihan').value = tagihanAktif;
            }
            updatePaymentUI();
        }
        let searchTimeout = null;
        function onKetikCari(e) {
            let q = document.getElementById('search_po_id').value.trim(), listEl = document.getElementById('dropdown_po_list');
            if(e.key === 'Enter') { e.preventDefault(); cariPO(); return; }
            if (q.length < 2) { listEl.classList.add('hidden'); listEl.innerHTML = ''; return; }
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                fetch('/api/search-po?q=' + encodeURIComponent(q)).then(r => r.json()).then(data => {
                    if (data.length === 0) { listEl.innerHTML = '<div class="p-3 text-xs text-gray-500 text-center font-bold">Tidak Ditemukan</div>'; listEl.classList.remove('hidden'); return; }
                    let html = ''; data.forEach(item => {
                        let badge = item.status_pelunasan === 'Sudah Lunas' ? '<span class="text-green-600 bg-green-100 px-1 rounded ml-1 text-[10px]">(Lunas)</span>' : '';
                        html += `<div onclick="pilihPO('${item.id_pesanan}')" class="p-3 hover:bg-blue-50 cursor-pointer border-b text-xs flex justify-between"><div><span class="font-bold">${item.nama_pelanggan}</span>${badge}<br><span class="text-gray-500 text-[10px]">${item.id_pesanan}</span></div><div class="font-bold text-pos">DP: Rp ${item.dp_diterima.toLocaleString('id-ID')}</div></div>`;
                    });
                    listEl.innerHTML = html; listEl.classList.remove('hidden');
                });
            }, 300);
        }
        function pilihPO(id) { document.getElementById('search_po_id').value = id; document.getElementById('dropdown_po_list').classList.add('hidden'); cariPO(); }
        function cariPO() {
            let idPO = document.getElementById('search_po_id').value.trim(), poStatusMsg = document.getElementById('po_status_msg');
            document.getElementById('dropdown_po_list').classList.add('hidden');
            if(!idPO) return;
            poStatusMsg.innerText = "⏳ Memeriksa..."; poStatusMsg.className = "text-xs mt-3 font-bold text-blue-600 block";
            fetch('/api/po/' + encodeURIComponent(idPO)).then(r => { if(!r.ok) throw new Error(); return r.json(); }).then(data => {
                if (data.status_pelunasan === "Sudah Lunas") { poStatusMsg.innerText = "⚠️ SUDAH LUNAS."; poStatusMsg.className = "text-xs mt-3 font-bold text-amber-700 bg-amber-100 p-2 rounded block"; resetHitungan(); return; }
                poStatusMsg.innerText = "✅ Ditemukan: " + data.nama_pelanggan; poStatusMsg.className = "text-xs mt-3 font-bold text-green-700 bg-green-100 p-2 rounded block";
                objPO = data; document.getElementById('sum_nama').innerText = data.nama_pelanggan; document.getElementById('sum_dp').innerText = "- Rp " + data.dp_diterima.toLocaleString('id-ID');
                document.getElementById('post_id_po').value = data.id_pesanan; document.getElementById('post_nama').value = data.nama_pelanggan;
                document.getElementById('input_aktual_golden').value = data.aktual_golden > 0 ? data.aktual_golden : (data.qty_golden * 1.5).toFixed(1);
                document.getElementById('input_aktual_white').value = data.aktual_white > 0 ? data.aktual_white : (data.qty_white * 1.5).toFixed(1);
                hitungTotalKasir();
            }).catch(() => { poStatusMsg.innerText = "❌ Tidak Ditemukan!"; poStatusMsg.className = "text-xs mt-3 font-bold text-red-700 bg-red-100 p-2 rounded block"; resetHitungan(); });
        }
        async function prosesTransaksi(e) {
            e.preventDefault();
            let btn = document.getElementById('btnSimpan'); btn.disabled = true; btn.innerText = "Menyimpan... ⏳";
            try {
                let formObj = new FormData(document.getElementById('form_pos'));
                let res = await (await fetch('/api/submit-pos', { method: 'POST', body: formObj })).json();
                if(res.status === 'success') {
                    lastTransactionData = res.trx;
                    document.getElementById('btnReprint').classList.remove('hidden');
                    cetakStrukEksekusi(res.trx);
                    alert("Transaksi Berhasil Disimpan di GSheets!");
                    setTimeout(() => window.location.reload(), 1500);
                }
            } catch(err) { alert("Error: " + err.message); btn.disabled = false; btn.innerText = "SIMPAN & CETAK STRUK 🖨️"; }
        }
        function cetakStrukEksekusi(trx) {
            document.getElementById('rc_id').innerText = "ID : " + trx.id_pos;
            document.getElementById('rc_tgl').innerText = "Tgl: " + trx.tanggal;
            document.getElementById('rc_nama').innerText = "Plg: " + trx.nama_pelanggan;
            document.getElementById('rc_tipe').innerText = "Tipe: " + trx.tipe_transaksi;
            let rincianHtml = "";
            if(trx.qty_golden > 0) rincianHtml += `<div>- Melon Golden: ${trx.qty_golden} Kg</div>`;
            if(trx.qty_white > 0) rincianHtml += `<div>- Melon White : ${trx.qty_white} Kg</div>`;
            document.getElementById('rc_rincian').innerHTML = rincianHtml || "<div>- Penjualan BUMDes</div>";
            document.getElementById('rc_sub').innerText = "Rp " + trx.total_tagihan.toLocaleString('id-ID');
            document.getElementById('rc_disk').innerText = trx.diskon_keterangan;
            document.getElementById('rc_tot').innerText = "Rp " + trx.total_tagihan.toLocaleString('id-ID');
            document.getElementById('rc_metode').innerText = trx.metode_pembayaran;
            document.getElementById('rc_bayar').innerText = "Rp " + trx.dibayar.toLocaleString('id-ID');
            if(trx.metode_pembayaran === 'Tunai') {
                document.getElementById('row_rc_kembali').style.display = 'flex';
                document.getElementById('rc_kembali').innerText = "Rp " + trx.kembalian.toLocaleString('id-ID');
            } else { document.getElementById('row_rc_kembali').style.display = 'none'; }

            let printMethod = document.querySelector('input[name="print_method"]:checked')?.value || 'browser';
            if(printMethod === 'bluetooth' && printCharacteristic) {
                kirimBluetoothESC(trx);
            } else {
                let content = document.getElementById('receipt_container').innerHTML;
                let win = window.open('', '', 'height=600,width=400');
                win.document.write('<html><head><title>Struk POS</title></head><body>');
                win.document.write(content);
                win.document.write('</body></html>');
                win.document.close();
                win.focus();
                setTimeout(() => { win.print(); win.close(); }, 300);
            }
        }
        function cetakUlangStruk() { if(lastTransactionData) cetakStrukEksekusi(lastTransactionData); else alert("Belum ada transaksi di sesi ini."); }
        function cetakStrukContoh() {
            let sampleTrx = {
                id_pos: "TRX-TEST01", tanggal: "2026-10-18 14:30", nama_pelanggan: "Bpk. Budi (Test)",
                tipe_transaksi: "Penjualan Langsung", qty_golden: 1.5, qty_white: 1.5,
                total_tagihan: 157500, diskon_keterangan: "-", dibayar: 200000, kembalian: 42500, metode_pembayaran: "Tunai"
            };
            cetakStrukEksekusi(sampleTrx);
        }
        async function pairBluetoothPrinter() {
            try {
                bluetoothDevice = await navigator.bluetooth.requestDevice({ acceptAllDevices: true, optionalServices: ['000018f0-0000-1000-8000-00805f9b34fb'] });
                let server = await bluetoothDevice.gatt.connect();
                let service = await server.getPrimaryService('000018f0-0000-1000-8000-00805f9b34fb');
                printCharacteristic = await service.getCharacteristic('00002af1-0000-1000-8000-00805f9b34fb');
                document.getElementById('status_bt').innerText = "Terhubung"; document.getElementById('status_bt').className = "text-[10px] px-2 py-0.5 rounded bg-green-100 text-green-700 font-bold";
                alert("Printer Bluetooth berhasil terhubung!");
            } catch(e) { alert("Koneksi Bluetooth gagal/dibatalkan: " + e.message); }
        }
        async function kirimBluetoothESC(trx) {
            if(!printCharacteristic) return;
            let encoder = new TextEncoder();
            let textData = `\x1B\x40\x1B\x61\x01BUMDES KEMBARAN\nPusat Buah Melon Berkualitas\n--------------------------------\nID: ${trx.id_pos}\nTgl: ${trx.tanggal}\nPlg: ${trx.nama_pelanggan}\n--------------------------------\nTotal: Rp ${trx.total_tagihan.toLocaleString('id-ID')}\nBayar: Rp ${trx.dibayar.toLocaleString('id-ID')}\nKembali: Rp ${trx.kembalian.toLocaleString('id-ID')}\n--------------------------------\nTerima Kasih!\n\n\n`;
            await printCharacteristic.writeValue(encoder.encode(textData));
        }
        function bukaModalPrinter() { document.getElementById('modal_printer').classList.remove('hidden'); }
        function tutupModalPrinter() { document.getElementById('modal_printer').classList.add('hidden'); }
    </script>
</body>
</html>
"""

ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Panel Admin BUMDes V53</title>
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

CONFIG_ADMIN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"><title>Setting Config</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 p-6">
    <div class="max-w-xl mx-auto bg-white rounded-2xl shadow p-6 space-y-6">
        <div class="flex justify-between items-center border-b pb-4"><h1 class="text-lg font-bold">⚙️ Pengaturan Aplikasi</h1><a href="/admin" class="text-xs bg-gray-200 px-3 py-1.5 rounded font-bold">Kembali</a></div>
        <form action="/save-config" method="POST" class="space-y-4">
            <div><label class="text-xs font-bold">Kuota Promo</label><input type="number" name="kuota_promo" value="{{ config.get('Kuota Promo', 0) }}" class="w-full p-2 border rounded text-sm" required></div>
            <div><label class="text-xs font-bold">Diskon (%)</label><input type="text" name="persen_diskon" value="{{ config.get('Persen Diskon', 0) }}" class="w-full p-2 border rounded text-sm" required></div>
            <div><label class="text-xs font-bold">Tanggal Panen</label><input type="text" name="tanggal_panen" value="{{ config.get('Tanggal Panen', '-') }}" class="w-full p-2 border rounded text-sm" required></div>
            <div><label class="text-xs font-bold">WA Utama</label><input type="text" name="wa_utama" value="{{ config.get('WA Admin Utama', '') }}" class="w-full p-2 border rounded text-sm" required></div>
            <div><label class="text-xs font-bold">WA Keuangan (Penerima DP)</label><input type="text" name="wa_keuangan" value="{{ config.get('WA Admin Keuangan', '') }}" class="w-full p-2 border rounded text-sm" required></div>
            <div><label class="text-xs font-bold">WA Kebun</label><input type="text" name="wa_kebun" value="{{ config.get('WA Admin Kebun', '') }}" class="w-full p-2 border rounded text-sm" required></div>
            <div><label class="text-xs font-bold">Harga Normal / Kg (Rp)</label><input type="text" name="harga_per_kg" value="{{ config.get('Harga Per Kg', 52500) }}" class="w-full p-2 border rounded text-sm" required></div>
            <button type="submit" class="w-full bg-orange-600 text-white font-bold py-3 rounded-lg shadow">Simpan & Sinkronkan 💾</button>
        </form>
    </div>
</body>
</html>
"""

LAPORAN_HTML = r"""
<!DOCTYPE html>
<html lang="id">
<head><meta charset="UTF-8"><title>Laporan Live G-Sheets</title><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-50 min-h-screen">
    <nav class="bg-white shadow-sm border-b px-6 py-4 flex justify-between items-center sticky top-0 z-50">
        <div class="flex items-center space-x-3"><span class="text-xl font-black text-emerald-600">📊 Laporan Live (Google Sheets)</span></div>
        <div class="flex space-x-3 text-sm">
            <a href="/admin-kebun" class="bg-emerald-600 text-white px-3 py-1.5 rounded font-bold text-xs shadow">👨‍🌾 Admin Kebun</a>
            <a href="/admin" class="bg-gray-800 text-white px-3 py-1.5 rounded font-bold text-xs shadow">← Kembali ke Admin</a>
        </div>
    </nav>
    <div class="max-w-7xl mx-auto p-4 md:p-6 space-y-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div class="bg-white p-5 rounded-2xl shadow-sm border"><h3 class="font-bold text-gray-800 border-b pb-2 mb-3 text-sm uppercase">🍈 Rekap per Produk</h3>
                <div class="flex justify-between mb-2"><span class="text-gray-600">Melon Golden Humi</span><span class="font-black text-orange-600">{{ "%.1f"|format(rekap_produk['Golden Humi']) }} KG</span></div>
                <div class="flex justify-between"><span class="text-gray-600">Melon White Humi</span><span class="font-black text-emerald-600">{{ "%.1f"|format(rekap_produk['White Humi']) }} KG</span></div>
            </div>
            <div class="bg-white p-5 rounded-2xl shadow-sm border"><h3 class="font-bold text-gray-800 border-b pb-2 mb-3 text-sm uppercase">💳 Rekap Metode Pembayaran</h3>
                {% for metode, total in rekap_metode.items() %}
                <div class="flex justify-between mb-2"><span class="text-gray-600">via {{ metode }}</span><span class="font-black text-blue-700">Rp {{ "{:,.0f}".format(total) }}</span></div>
                {% endfor %}
            </div>
        </div>
        <div class="bg-white rounded-2xl shadow-sm border overflow-hidden">
            <div class="p-4 bg-gray-100 border-b font-bold text-sm">🧾 Detail Transaksi Penjualan</div>
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm whitespace-nowrap">
                    <thead class="bg-gray-50 text-gray-600 text-xs uppercase border-b"><tr><th class="p-4">ID / Waktu</th><th class="p-4">Pelanggan & Info</th><th class="p-4">Rincian (KG)</th><th class="p-4 text-right">Total</th><th class="p-4 text-center">Metode</th></tr></thead>
                    <tbody class="divide-y divide-gray-100">
                        {% for t in transaksi %}
                        <tr class="hover:bg-gray-50">
                            <td class="p-4 font-bold text-gray-800">{{ t.id_pos }}<br><span class="font-normal text-xs text-gray-400">{{ t.tanggal }}</span></td>
                            <td class="p-4 font-semibold text-gray-800">{{ t.nama_pelanggan }}<br><span class="text-xs text-blue-600">{{ t.tipe_transaksi }} | Ref: {{ t.id_referensi }}</span></td>
                            <td class="p-4 text-xs font-semibold">Golden: {{ "%.1f"|format(t.qty_golden) }} | White: {{ "%.1f"|format(t.qty_white) }}</td>
                            <td class="p-4 text-right font-black">Rp {{ "{:,.0f}".format(t.total_tagihan) }}</td>
                            <td class="p-4 text-center"><span class="bg-green-100 text-green-800 px-2 py-1 rounded text-[10px] font-bold">{{ t.metode_pembayaran }}</span></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""

# ======================= ENDPOINTS (REST API) =======================

@app.get("/", response_class=HTMLResponse)
def root(): return RedirectResponse(url="/pre-order")

@app.get("/pre-order", response_class=HTMLResponse)
def pre_order_page(): return HTMLResponse(content=Template(PRE_ORDER_HTML).render(config=get_app_config()))

@app.get("/pos", response_class=HTMLResponse)
def pos_page(request: Request): return HTMLResponse(content=Template(POS_HTML).render(config=get_app_config()))

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
                
    # Direct URL Bypass untuk QRIS Instan (Anti Delay/Kosong)
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
    pesan_wa = f"Halo Admin Keuangan, saya sudah transfer DP sebesar Rp {dp:,.0f} untuk ID Pesanan {id}. Berikut bukti transfernya:"
    wa_link = f"https://api.whatsapp.com/send?phone={wa_keuangan}&text={urllib.parse.quote(pesan_wa)}"
    
    return HTMLResponse(content=Template(SUCCESS_HTML).render(order=order_dict, qris_url_encoded=dq, wa_link=wa_link))

@app.get("/api/qris")
def get_qris_api(amount: float):
    dq = create_dynamic_qris(STATIC_QRIS, amount)
    return {"qris_string": dq, "qris_url": f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(dq)}"}

@app.post("/api/submit-pos")
def api_submit_pos(
    tipe_transaksi: str = Form(...), id_po: str = Form(""), nama_pelanggan: str = Form("Pelanggan Umum"),
    qty_golden: float = Form(0.0), qty_white: float = Form(0.0), diskon_keterangan: str = Form("-"),
    tagihan_aktif: float = Form(0.0), nominal_bayar: float = Form(0.0), metode_pembayaran: str = Form("Tunai")
):
    kembalian = nominal_bayar - tagihan_aktif if metode_pembayaran == "Tunai" else 0.0
    if metode_pembayaran == "QRIS": nominal_bayar = tagihan_aktif
    id_pos = f"TRX-{datetime.now().strftime('%d%H%M%S')}"
    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    sheet_pos = get_gspread_sheet("POS")
    if sheet_pos:
        sheet_pos.append_row([id_pos, tanggal, tipe_transaksi, id_po if (tipe_transaksi == "Pelunasan PO" and id_po) else "-", nama_pelanggan, qty_golden, qty_white, diskon_keterangan or "-", tagihan_aktif, nominal_bayar, kembalian, metode_pembayaran])
        
    if tipe_transaksi == "Pelunasan PO" and id_po:
        sheet_po_data = get_gspread_sheet("DataPemesan")
        if sheet_po_data:
            records = sheet_po_data.get_all_values()
            for i, row in enumerate(records[1:], start=2):
                if len(row) > 0 and row[0] == id_po:
                    sheet_po_data.update_cell(i, 18, "Sudah Lunas")
                    break
                    
    trx_dict = {
        "id_pos": id_pos, "tanggal": tanggal, "tipe_transaksi": tipe_transaksi,
        "nama_pelanggan": nama_pelanggan, "qty_golden": qty_golden, "qty_white": qty_white,
        "diskon_keterangan": diskon_keterangan or "-", "total_tagihan": tagihan_aktif,
        "dibayar": nominal_bayar, "kembalian": kembalian, "metode_pembayaran": metode_pembayaran
    }
    return {"status": "success", "trx": trx_dict}

@app.get("/api/search-po")
def search_po_api(q: str):
    sheet = get_gspread_sheet("DataPemesan")
    results = []
    if sheet:
        records = sheet.get_all_values()
        if len(records) > 1:
            headers = records[0]
            for row in records[1:]:
                if len(row) > 0:
                    id_p = str(row[0])
                    nama = str(row[2]) if len(row) > 2 else ""
                    if q.lower() in id_p.lower() or q.lower() in nama.lower():
                        tot = safe_float(row[5]) if len(row) > 5 else 0.0
                        dp_terima = safe_float(row[7]) if len(row) > 7 else 0.0
                        sisa = tot - dp_terima
                        results.append({
                            "id_pesanan": id_p, "nama_pelanggan": nama,
                            "qty_golden": int(safe_float(row[9] if len(row) > 9 else 0)), 
                            "qty_white": int(safe_float(row[10] if len(row) > 10 else 0)),
                            "total_tagihan": tot, "dp_diterima": dp_terima,
                            "sisa_tagihan": sisa if sisa > 0 else 0, 
                            "status_pelunasan": str(row[17]) if len(row) > 17 else "Belum"
                        })
    return results[:15]

@app.get("/api/po/{query_str}")
def get_po_api(query_str: str):
    sheet = get_gspread_sheet("DataPemesan")
    if sheet:
        records = sheet.get_all_values()
        if len(records) > 1:
            for row in records[1:]:
                if len(row) > 0:
                    id_p = str(row[0])
                    nama = str(row[2]) if len(row) > 2 else ""
                    if query_str == id_p or query_str.lower() in id_p.lower() or query_str.lower() in nama.lower():
                        tot = safe_float(row[5]) if len(row) > 5 else 0.0
                        dp_terima = safe_float(row[7]) if len(row) > 7 else 0.0
                        sisa = tot - dp_terima
                        return {
                            "id_pesanan": id_p, "nama_pelanggan": nama,
                            "qty_golden": int(safe_float(row[9] if len(row) > 9 else 0)), 
                            "qty_white": int(safe_float(row[10] if len(row) > 10 else 0)),
                            "aktual_golden": safe_float(row[15] if len(row) > 15 else 0), 
                            "aktual_white": safe_float(row[16] if len(row) > 16 else 0),
                            "total_tagihan": tot, "dp_diterima": dp_terima,
                            "sisa_tagihan": sisa if sisa > 0 else 0, 
                            "status_pelunasan": str(row[17]) if len(row) > 17 else "Belum"
                        }
    raise HTTPException(status_code=404, detail="PO Tidak Ditemukan")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard():
    sheet = get_gspread_sheet("DataPemesan")
    pl = []
    t_dp = 0.0
    lunas_count, belum_count = 0, 0
    if sheet:
        records = sheet.get_all_values()
        if len(records) > 1:
            for row in records[1:]:
                if len(row) > 0 and row[0]:
                    dp_terima = safe_float(row[7] if len(row) > 7 else 0)
                    status_dp = str(row[8] if len(row) > 8 else "Belum")
                    t_dp += dp_terima
                    if status_dp == "Sudah": lunas_count += 1
                    else: belum_count += 1
                    
                    pl.append({
                        "id_pesanan": str(row[0]), "tanggal_transaksi": str(row[1] if len(row)>1 else ""),
                        "nama_pelanggan": str(row[2] if len(row)>2 else ""), "no_whatsapp": str(row[3] if len(row)>3 else ""),
                        "qty_golden": safe_float(row[9] if len(row)>9 else 0), "qty_white": safe_float(row[10] if len(row)>10 else 0),
                        "total_tagihan": safe_float(row[5] if len(row)>5 else 0), "nominal_dp": safe_float(row[6] if len(row)>6 else 0),
                        "nominal_dp_diterima": dp_terima, "status_dp": status_dp,
                        "status_pelunasan": str(row[17] if len(row)>17 else "Belum")
                    })
    return Template(ADMIN_HTML).render(pesanan_list=pl, config=get_app_config(), total_dp_masuk=t_dp, lunas_count=lunas_count, belum_count=belum_count)

@app.get("/admin-kebun", response_class=HTMLResponse)
def admin_kebun_page():
    sheet_po = get_gspread_sheet("DataPemesan")
    sheet_stok = get_gspread_sheet("Stok_Kebun")
    
    pesanan_list = []
    if sheet_po:
        records = sheet_po.get_all_values()
        if len(records) > 1:
            for row in records[1:]:
                if len(row) > 17:
                    if str(row[8]) == "Sudah" and str(row[17]) != "Sudah Lunas":
                        pesanan_list.append({
                            "id_pesanan": str(row[0]), "nama_pelanggan": str(row[2]), "no_whatsapp": str(row[3]),
                            "qty_golden": safe_float(row[9]), "qty_white": safe_float(row[10])
                        })
                        
    stok_g, stok_w = [], []
    denah = {l: {b: [] for b in range(1, 11)} for l in ['A','B','C','D','E','F','G']}
    if sheet_stok:
        s_records = sheet_stok.get_all_values()
        if len(s_records) > 1:
            for s in s_records[1:]:
                if len(s) > 0:
                    lajur = str(s[1] if len(s)>1 else "")
                    baris = int(safe_float(s[2] if len(s)>2 else 0))
                    item = {"id": str(s[0]), "jenis": str(s[3] if len(s)>3 else ""), "berat": safe_float(s[4] if len(s)>4 else 0), "status": str(s[5] if len(s)>5 else ""), "pemesan": str(s[7] if len(s)>7 else "-")}
                    if lajur in denah and 1 <= baris <= 10: denah[lajur][baris].append(item)
                    if item["jenis"] == "Golden": stok_g.append(item)
                    elif item["jenis"] == "White": stok_w.append(item)
                    
    return Template(ADMIN_KEBUN_HTML).render(pesanan_list=pesanan_list, denah=denah, stok_g=stok_g, stok_w=stok_w)

@app.post("/input-stok")
def input_stok(lajur: str = Form(...), baris: int = Form(...), jenis_buah: str = Form(...), berat: float = Form(...)):
    sheet = get_gspread_sheet("Stok_Kebun")
    if sheet:
        id_stok = f"{jenis_buah}-{lajur}-{baris}"
        records = sheet.get_all_values()
        found_row = -1
        for i, row in enumerate(records[1:], start=2):
            if len(row) > 0 and row[0] == id_stok:
                found_row = i
                break
        if found_row != -1:
            sheet.update_cell(found_row, 5, berat)
            sheet.update_cell(found_row, 6, "Tersedia")
        else:
            sheet.append_row([id_stok, lajur, baris, jenis_buah, berat, "Tersedia", "", ""])
    return RedirectResponse(url="/admin-kebun", status_code=303)

@app.get("/hapus-stok/{id_stok}")
def hapus_stok(id_stok: str):
    sheet = get_gspread_sheet("Stok_Kebun")
    if sheet:
        records = sheet.get_all_values()
        for i, row in enumerate(records[1:], start=2):
            if len(row) > 0 and row[0] == id_stok:
                sheet.delete_rows(i)
                break
    return RedirectResponse(url="/admin-kebun", status_code=303)

@app.post("/update-kebun/{id_pesanan}")
def update_kebun(id_pesanan: str, id_sg: str = Form(""), id_sw: str = Form("")):
    sheet_po = get_gspread_sheet("DataPemesan")
    sheet_stok = get_gspread_sheet("Stok_Kebun")
    
    if sheet_stok:
        s_records = sheet_stok.get_all_values()
        for i, row in enumerate(s_records[1:], start=2):
            if len(row) > 6 and row[6] == id_pesanan:
                sheet_stok.update_cell(i, 6, "Tersedia")
                sheet_stok.update_cell(i, 7, "")
                sheet_stok.update_cell(i, 8, "")
                
    lg, bg, ag, lw, bw, aw = "-", 0, 0.0, "-", 0, 0.0
    nama_pelanggan = ""
    
    if sheet_po:
        p_records = sheet_po.get_all_values()
        for i, row in enumerate(p_records[1:], start=2):
            if len(row) > 0 and row[0] == id_pesanan:
                nama_pelanggan = row[2]
                break

    if sheet_stok and (id_sg or id_sw):
        s_records = sheet_stok.get_all_values()
        for i, row in enumerate(s_records[1:], start=2):
            if len(row) > 0:
                if row[0] == id_sg:
                    sheet_stok.update_cell(i, 6, "Dipesan")
                    sheet_stok.update_cell(i, 7, id_pesanan)
                    sheet_stok.update_cell(i, 8, nama_pelanggan)
                    lg, bg, ag = row[1], int(row[2]), safe_float(row[4])
                elif row[0] == id_sw:
                    sheet_stok.update_cell(i, 6, "Dipesan")
                    sheet_stok.update_cell(i, 7, id_pesanan)
                    sheet_stok.update_cell(i, 8, nama_pelanggan)
                    lw, bw, aw = row[1], int(row[2]), safe_float(row[4])

    if sheet_po:
        p_records = sheet_po.get_all_values()
        for i, row in enumerate(p_records[1:], start=2):
            if len(row) > 0 and row[0] == id_pesanan:
                sheet_po.update_cell(i, 12, lg); sheet_po.update_cell(i, 13, bg)
                sheet_po.update_cell(i, 14, lw); sheet_po.update_cell(i, 15, bw)
                sheet_po.update_cell(i, 16, ag); sheet_po.update_cell(i, 17, aw)
                break
    return {"status": "success"}

@app.get("/laporan", response_class=HTMLResponse)
def laporan_page():
    sheet = get_gspread_sheet("POS")
    transaksi = []
    if sheet:
        try:
            records = sheet.get_all_values()
            if len(records) > 1:
                for row in records[1:]:
                    if len(row) > 0 and row[0]:
                        transaksi.append({
                            "id_pos": str(row[0]), "tanggal": str(row[1] if len(row)>1 else ""),
                            "tipe_transaksi": str(row[2] if len(row)>2 else ""), "id_referensi": str(row[3] if len(row)>3 else "-"),
                            "nama_pelanggan": str(row[4] if len(row)>4 else ""),
                            "qty_golden": safe_float(row[5] if len(row)>5 else 0),
                            "qty_white": safe_float(row[6] if len(row)>6 else 0),
                            "total_tagihan": safe_float(row[8] if len(row)>8 else 0),
                            "metode_pembayaran": str(row[11] if len(row)>11 else "Tunai")
                        })
        except Exception: pass
    rekap_metode = {"Tunai": 0, "QRIS": 0}
    rekap_produk = {"Golden Humi": 0, "White Humi": 0}
    for t in transaksi:
        rekap_metode[t["metode_pembayaran"]] = rekap_metode.get(t["metode_pembayaran"], 0) + t["total_tagihan"]
        rekap_produk["Golden Humi"] += t["qty_golden"]
        rekap_produk["White Humi"] += t["qty_white"]
    transaksi.reverse()
    return HTMLResponse(content=Template(LAPORAN_HTML).render(transaksi=transaksi, rekap_metode=rekap_metode, rekap_produk=rekap_produk))

@app.get("/config-admin", response_class=HTMLResponse)
def config_form(): return HTMLResponse(content=Template(CONFIG_ADMIN_HTML).render(config=get_app_config()))

@app.post("/save-config")
def save_config(kuota_promo: int=Form(...), persen_diskon: str=Form(...), tanggal_panen: str=Form(...), wa_utama: str=Form(...), wa_keuangan: str=Form(...), wa_kebun: str=Form(...), harga_per_kg: str=Form(...)):
    sheet = get_gspread_sheet("Config")
    if sheet:
        try:
            sheet.clear()
            sheet.append_row(["Kuota Promo", "Persen Diskon", "Tanggal Panen", "WA Admin Utama", "WA Admin Keuangan", "WA Admin Kebun", "Harga Per Kg"])
            sheet.append_row([kuota_promo, persen_diskon, tanggal_panen, wa_utama, wa_keuangan, wa_kebun, harga_per_kg])
        except Exception: pass
    return RedirectResponse(url="/admin", status_code=303)

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

@app.post("/delete-orders")
async def delete_orders(request: Request):
    fd = await request.form()
    ids = fd.getlist('ids_to_delete')
    if not ids: return RedirectResponse(url="/admin", status_code=303)
    sheet = get_gspread_sheet("DataPemesan")
    if sheet:
        try:
            records = sheet.get_all_values()
            for i in range(len(records) - 1, 0, -1):
                if len(records[i]) > 0 and records[i][0] in ids: sheet.delete_rows(i + 1)
        except Exception: pass
    return RedirectResponse(url="/admin", status_code=303)
