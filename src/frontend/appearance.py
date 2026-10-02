"""Panel pengaturan tampilan di browser."""

import streamlit as st

try:
    import streamlit.components.v1 as components
except Exception:  # pragma: no cover - versi Streamlit tanpa components
    components = None


def render_appearance_editor():
    """
    Panel mengambang untuk mengubah tampilan (ukuran teks, warna aksen, mode
    terang/gelap) langsung dari browser. Semua perubahan HANYA berupa CSS/JS
    yang disuntikkan ke halaman saat ini, tidak disimpan ke cookie/localStorage
    maupun ke file sumber. Refresh browser = tampilan kembali ke default.
    """
    html = """
        <script>
        (function() {
            const doc = window.parent.document;
            if (doc.getElementById('__mt_editor_btn')) return; // sudah ada, jangan duplikat

            // Gaya panel (hidup di dokumen induk, bukan di dalam iframe)
            const panelStyle = doc.createElement('style');
            panelStyle.id = '__mt_editor_style';
            panelStyle.innerHTML = `
                #__mt_editor_btn {
                    position: fixed; bottom: 22px; right: 22px; z-index: 999999;
                    width: 46px; height: 46px; border-radius: 50%;
                    background: #0f172a; color: #fff; border: none; font-size: 19px;
                    cursor: pointer; box-shadow: 0 6px 18px rgba(15,23,42,.35);
                }
                #__mt_editor_btn:hover { background: #0f766e; }
                #__mt_editor_panel {
                    position: fixed; bottom: 78px; right: 22px; z-index: 999999;
                    width: 272px; background: #ffffff; color: #0f172a;
                    border: 1px solid #e3e8ee; border-radius: 14px; padding: 16px;
                    box-shadow: 0 12px 32px rgba(15,23,42,.22); font-family: sans-serif; display: none;
                }
                #__mt_editor_panel h4 { margin: 0 0 3px 0; font-size: 13.5px; color: #0f172a; }
                #__mt_editor_panel .sub { font-size: 11px; color: #64748b; margin-bottom: 4px; }
                #__mt_editor_panel label { font-size: 11.5px; color: #334155; display:block; margin-top:11px; font-weight:600; }
                #__mt_editor_panel .row { display:flex; gap:6px; margin-top:5px; }
                #__mt_editor_panel button.opt {
                    flex:1; padding:7px 4px; font-size:11px; border-radius:7px;
                    border:1px solid #d7dee6; background:#f7f9fb; color:#334155; cursor:pointer;
                }
                #__mt_editor_panel button.opt:hover { border-color:#0f766e; }
                #__mt_editor_panel button.opt.active { background:#0f766e; border-color:#0f766e; color:#ffffff; }
                #__mt_editor_reset {
                    margin-top: 14px; width:100%; padding:8px; border-radius:8px;
                    background:#f1f5f9; border:1px solid #d7dee6; color:#334155; cursor:pointer; font-size:12px;
                }
                #__mt_editor_note { font-size:10.5px; color:#94a3b8; margin-top:10px; line-height:1.45; }
            `;
            doc.head.appendChild(panelStyle);

            // Dua style dinamis: satu untuk ukuran teks, satu untuk warna aksen
            const scaleStyle = doc.createElement('style');
            scaleStyle.id = '__mt_scale_override';
            doc.head.appendChild(scaleStyle);
            const colorStyle = doc.createElement('style');
            colorStyle.id = '__mt_color_override';
            doc.head.appendChild(colorStyle);

            // Tombol gear
            const btn = doc.createElement('button');
            btn.id = '__mt_editor_btn';
            btn.title = 'Pengaturan tampilan (sementara)';
            btn.innerText = '🎨';
            doc.body.appendChild(btn);

            // Panel
            const panel = doc.createElement('div');
            panel.id = '__mt_editor_panel';
            panel.innerHTML = `
                <h4>🎨 Pengaturan Tampilan</h4>
                <div class="sub">Hanya tampilan di browsermu — data tidak berubah.</div>
                <label>Ukuran teks</label>
                <div class="row">
                    <button class="opt" data-scale="0.9">Kecil</button>
                    <button class="opt active" data-scale="1.0">Normal</button>
                    <button class="opt" data-scale="1.15">Besar</button>
                </div>
                <label>Warna aksen</label>
                <div class="row">
                    <button class="opt active" data-color="#0f766e">Teal</button>
                    <button class="opt" data-color="#1d4ed8">Biru</button>
                    <button class="opt" data-color="#6d28d9">Ungu</button>
                    <button class="opt" data-color="#b45309">Cokelat</button>
                </div>
                <label>Mode tampilan</label>
                <div class="row">
                    <button class="opt active" id="__mt_light">☀️ Terang</button>
                    <button class="opt" id="__mt_dark">🌙 Gelap</button>
                </div>
                <button id="__mt_editor_reset">↺ Kembalikan tampilan asli</button>
                <div id="__mt_editor_note">Perubahan bersifat sementara dan tidak disimpan. Refresh halaman untuk kembali ke tampilan asli.</div>
            `;
            doc.body.appendChild(panel);

            btn.addEventListener('click', () => {
                panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
            });

            function setActive(selector, el) {
                panel.querySelectorAll(selector).forEach(b => b.classList.remove('active'));
                el.classList.add('active');
            }
            function applyScale(scale) {
                scaleStyle.innerHTML = `html{font-size:${scale * 100}% !important;}`;
            }
            function applyColor(color) {
                colorStyle.innerHTML =
                    `body{--mt-accent:${color} !important;--mt-accent-soft:${color}22 !important;}` +
                    `body.__mt_dark{--mt-accent:${color} !important;}`;
            }
            /* Mode gelap adalah CLASS DI BODY, sedangkan Streamlit sering
               mengganti elemen <body> saat render ulang. Karena itu pilihan
               mode disimpan di localStorage dan diamankan MutationObserver,
               supaya warna gelap tidak "hilang" di tengah interaksi
               (mis. saat checkbox atau expander dibuka). */
            const KUNCI = '__mt_mode';
            function setMode(dark, simpan = true) {
                if (simpan) { try { localStorage.setItem(KUNCI, dark ? 'dark' : 'light'); } catch (e) {} }
                doc.body.classList.toggle('__mt_dark', dark);
                markMode(dark);
            }
            function markMode(dark) {
                const l = doc.getElementById('__mt_light');
                const g = doc.getElementById('__mt_dark');
                if (l) l.classList.toggle('active', !dark);
                if (g) g.classList.toggle('active', dark);
            }
            /* Pasang ulang class setiap kali <body> baru dibuat. */
            new MutationObserver(() => {
                let mode = 'light';
                try { mode = localStorage.getItem(KUNCI) || 'light'; } catch (e) {}
                doc.body.classList.toggle('__mt_dark', mode === 'dark');
            }).observe(doc.documentElement, { childList: true, subtree: true });
            /* Terapkan mode tersimpan saat panel dibuka. */
            try { setMode((localStorage.getItem(KUNCI) || 'light') === 'dark', false); }
            catch (e) { setMode(false, false); }

            panel.querySelectorAll('[data-scale]').forEach(b => {
                b.addEventListener('click', () => {
                    applyScale(parseFloat(b.dataset.scale));
                    setActive('[data-scale]', b);
                });
            });
            panel.querySelectorAll('[data-color]').forEach(b => {
                b.addEventListener('click', () => {
                    applyColor(b.dataset.color);
                    setActive('[data-color]', b);
                });
            });
            doc.getElementById('__mt_dark').addEventListener('click', () => {
                setMode(true);
            });
            doc.getElementById('__mt_light').addEventListener('click', () => {
                setMode(false);
            });
            doc.getElementById('__mt_editor_reset').addEventListener('click', () => {
                scaleStyle.innerHTML = '';
                colorStyle.innerHTML = '';
                panel.querySelectorAll('.opt').forEach(b => b.classList.remove('active'));
                panel.querySelector('[data-scale="1.0"]').classList.add('active');
                panel.querySelector('[data-color="#0f766e"]').classList.add('active');
                setMode(false);
            });
        })();
        </script>
        """
    if hasattr(st, "iframe"):
        # height=1px: kontainer tak terlihat untuk script panel (Streamlit tidak
        # mengizinkan tinggi 0 pada st.iframe).
        st.iframe(html, height=1)
    elif components is not None:  # fallback untuk Streamlit versi lama
        components.html(html, height=0)
