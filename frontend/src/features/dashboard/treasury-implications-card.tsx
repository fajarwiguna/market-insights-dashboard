"use client";

import { useState } from "react";
import type { MarketReport } from "@/lib/api/types";

const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const decimalFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bpFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 0, maximumFractionDigits: 1 });

function findMetric(report: MarketReport, section: "fx" | "indices" | "yields" | "commodities", fragments: string[]) {
  const dict = report[section];
  if (!dict || typeof dict !== "object") return null;
  for (const [key, val] of Object.entries(dict)) {
    const lower = key.toLowerCase();
    if (fragments.some((f) => lower.includes(f.toLowerCase()))) {
      return [key, val] as const;
    }
  }
  return null;
}

export function TreasuryImplicationsCard({ report }: { report: MarketReport }) {
  const [isOpen, setIsOpen] = useState(false);

  const usd = findMetric(report, "fx", ["USD/IDR"])?.[1];
  const sbn = findMetric(report, "yields", ["ID SBN 10 Tahun", "ID SBN 10Y", "SBN 10"])?.[1];
  const ust = findMetric(report, "yields", ["US Treasury 10 Tahun", "US Treasury 10Y", "US 10Y"])?.[1];
  const ihsg = findMetric(report, "indices", ["IHSG"])?.[1];
  const bi = report.bi && typeof report.bi === "object" ? report.bi : {};

  const biRateVal = typeof bi["BI Rate"] === "number" ? bi["BI Rate"] : report.macro_indicators?.["BI Rate (%)"]?.today ?? 5.75;
  const indoniaVal = typeof bi.INDONIA === "number" ? bi.INDONIA : 5.75;
  const spreadVal = typeof report.spread_sbn10_ust10_bp === "number" ? report.spread_sbn10_ust10_bp : 225;

  const usdToday = typeof usd?.today === "number" ? usd.today : null;
  const usdChg = typeof usd?.change_pct === "number" ? usd.change_pct : (typeof usd?.dtd_pct === "number" ? usd.dtd_pct : null);

  const sbnToday = typeof sbn?.today === "number" ? sbn.today : null;
  const sbnChg = typeof sbn?.dtd_bp === "number" ? sbn.dtd_bp : (typeof sbn?.change_bp === "number" ? sbn.change_bp : null);

  const ustToday = typeof ust?.today === "number" ? ust.today : null;
  const ihsgChg = typeof ihsg?.change_pct === "number" ? ihsg.change_pct : (typeof ihsg?.dtd_pct === "number" ? ihsg.dtd_pct : null);

  // Pillars from backend if present
  const backendPillars = report.treasury_implications ?? [];

  const toggleOpen = () => {
    setIsOpen((prev) => !prev);
  };

  const handleClose = () => {
    setIsOpen(false);
    document.getElementById("impacts")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <>
      {/* Trigger Card di sebelah Insight Hari Ini */}
      <article
        className={`treasury-card ${isOpen ? "treasury-card-active" : ""}`}
        id="impacts"
        onClick={toggleOpen}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleOpen();
          }
        }}
        aria-expanded={isOpen}
        aria-controls="treasury-inline-panel"
        aria-label="Buka narasi implikasi bagi Treasury"
      >
        <div className="treasury-card-inner">
          <div className="treasury-icon-box" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <line x1="10" y1="9" x2="8" y2="9" />
            </svg>
          </div>
          <div className="treasury-content">
            <h3 className="treasury-title">Implikasi bagi Treasury</h3>
            <p className="treasury-desc">
              Pantau pergerakan rupiah, spread obligasi, dan kondisi likuiditas dalam penetapan posisi pasar.
            </p>
            <button
              type="button"
              className="treasury-link"
              onClick={(e) => {
                e.stopPropagation();
                toggleOpen();
              }}
              aria-label={isOpen ? "Tutup analisis treasury" : "Baca analisis lengkap treasury"}
            >
              <span>{isOpen ? "Tutup analisis" : "Baca analisis lengkap"}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transition: "transform 0.2s ease", transform: isOpen ? "rotate(180deg)" : "none" }} aria-hidden="true">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          </div>
        </div>
      </article>

      {/* Narasi yang Dibungkus (Inline Panel pada Halaman yang Sama) */}
      {isOpen && (
        <section
          id="treasury-inline-panel"
          className="treasury-inline-panel"
          aria-labelledby="treasury-inline-title"
        >
          {/* Header Panel */}
          <div className="treasury-panel-header">
            <div className="treasury-panel-title-wrap">
              <div className="treasury-panel-icon" aria-hidden="true">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <line x1="10" y1="9" x2="8" y2="9" />
                </svg>
              </div>
              <div>
                <p className="eyebrow treasury-panel-eyebrow" style={{ marginBottom: "2px" }}>ANALISIS INTERNAL TREASURY</p>
                <h2 id="treasury-inline-title" className="treasury-panel-heading">
                  Implikasi Pasar &amp; Panduan Posisi Treasury
                </h2>
              </div>
            </div>
            <button
              type="button"
              className="treasury-panel-close-btn"
              onClick={handleClose}
              aria-label="Tutup panel analisis treasury"
            >
              <span>Tutup</span>
            </button>
          </div>

          {/* Key Metrics Quick Bar */}
          <div className="treasury-stats-grid">
            <div className="treasury-stat-item">
              <span className="treasury-stat-label">USD / IDR</span>
              <strong className="treasury-stat-value">
                {usdToday ? `Rp${numberFormat.format(usdToday)}` : "—"}
              </strong>
              <span className={`treasury-stat-sub ${usdChg && usdChg > 0 ? "sub-bad" : "sub-good"}`}>
                {usdChg !== null ? `${usdChg > 0 ? "+" : ""}${decimalFormat.format(usdChg)}%` : "0,00%"}
              </span>
            </div>

            <div className="treasury-stat-item">
              <span className="treasury-stat-label">SBN 10Y Yield</span>
              <strong className="treasury-stat-value">
                {sbnToday ? `${decimalFormat.format(sbnToday)}%` : "—"}
              </strong>
              <span className={`treasury-stat-sub ${sbnChg && sbnChg > 0 ? "sub-bad" : "sub-good"}`}>
                {sbnChg !== null ? `${sbnChg > 0 ? "+" : ""}${bpFormat.format(sbnChg)} bps` : "0 bps"}
              </span>
            </div>

            <div className="treasury-stat-item">
              <span className="treasury-stat-label">Spread RI–AS (10Y)</span>
              <strong className="treasury-stat-value">
                {typeof spreadVal === "number" ? `${numberFormat.format(spreadVal)} bps` : "—"}
              </strong>
              <span className="treasury-stat-sub sub-neutral">
                {ustToday ? `UST ${decimalFormat.format(ustToday)}%` : "Acuan Pasar"}
              </span>
            </div>

            <div className="treasury-stat-item">
              <span className="treasury-stat-label">BI Rate / INDONIA</span>
              <strong className="treasury-stat-value">
                {typeof biRateVal === "number" ? `${decimalFormat.format(biRateVal)}%` : "5,75%"}
              </strong>
              <span className="treasury-stat-sub sub-neutral">
                INDONIA {typeof indoniaVal === "number" ? `${decimalFormat.format(indoniaVal)}%` : "5,75%"}
              </span>
            </div>
          </div>

          {/* Strategic Context Box */}
          <div className="treasury-lead-box">
            <p className="treasury-lead-text">
              Dinamika pasar hari ini menuntut penyesuaian posisi taktis pada portofolio Treasury. Fluktuasi nilai tukar Rupiah,
              pergerakan imbal hasil obligasi negara, serta ketersediaan likuiditas di pasar uang menjadi indikator utama dalam
              menjaga stabilitas neraca bank dan optimalisasi imbal hasil aset.
            </p>
          </div>

          {/* 4 Core Strategic Pillars */}
          <div className="treasury-pillars-list">
            {backendPillars.length > 0 ? (
              backendPillars.map((pillar, idx) => (
                <div key={pillar.id ?? idx} className="treasury-pillar-card">
                  <div className="treasury-pillar-header">
                    <h4 className="treasury-pillar-title">{pillar.title}</h4>
                    {pillar.badge && <span className="treasury-pillar-badge">{pillar.badge}</span>}
                  </div>
                  {pillar.analysis && <p className="treasury-pillar-analysis">{pillar.analysis}</p>}
                  {pillar.recommendation && (
                    <div className="treasury-pillar-rec-box">
                      <strong className="treasury-rec-label">Rekomendasi Tindakan:</strong>
                      <p className="treasury-rec-text">{pillar.recommendation}</p>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <>
                {/* Pillar 1: FX Risk */}
                <div className="treasury-pillar-card">
                  <div className="treasury-pillar-header">
                    <h4 className="treasury-pillar-title">1. Pasar Valas &amp; Manajemen Risiko Nilai Tukar</h4>
                    <span className="treasury-pillar-badge">
                      {usdChg && usdChg > 0.15 ? "Pelemahan Rupiah" : usdChg && usdChg < -0.15 ? "Penguatan Rupiah" : "Stabil"}
                    </span>
                  </div>
                  <p className="treasury-pillar-analysis">
                    {usdToday
                      ? `Rupiah berada di posisi Rp${numberFormat.format(usdToday)} per dolar AS${usdChg !== null ? ` (${usdChg > 0 ? "melemah" : "menguat"} ${decimalFormat.format(Math.abs(usdChg))}%)` : ""}. Pelemahan nilai tukar meningkatkan kebutuhan lindung nilai valas dan sensitivitas likuiditas valas korporasi.`
                      : "Volatilitas kurs valuta asing memerlukan pemantauan ketat terhadap pergerakan arus dana antarbank dan kebutuhan valas nasabah."}
                  </p>
                  <div className="treasury-pillar-rec-box">
                    <strong className="treasury-rec-label">Rekomendasi Tindakan:</strong>
                    <ul className="treasury-rec-list">
                      <li>Perketat pengawasan <em>Net Open Position</em> (NOP / PDN) agar berada dalam batas aman regulasi dan selera risiko bank.</li>
                      <li>Sesuaikan kuotasi <em>bid-ask spread</em> pada client desk guna memitigasi risiko volatilitas harga valas intraday.</li>
                      <li>Gunakan instrumen lindung nilai (DNDF dan FX Swap) bersama Bank Indonesia untuk mengamankan posisi pasokan valas.</li>
                    </ul>
                  </div>
                </div>

                {/* Pillar 2: Fixed Income */}
                <div className="treasury-pillar-card">
                  <div className="treasury-pillar-header">
                    <h4 className="treasury-pillar-title">2. Portofolio Fixed Income (SBN &amp; SBSN)</h4>
                    <span className="treasury-pillar-badge">
                      {sbnChg && sbnChg > 1 ? "Yield Menanjak" : sbnChg && sbnChg < -1 ? "Yield Melandai" : "Yield Konsolidatif"}
                    </span>
                  </div>
                  <p className="treasury-pillar-analysis">
                    {sbnToday
                      ? `Yield SBN 10 Tahun berada di level ${decimalFormat.format(sbnToday)}%${sbnChg !== null ? ` (${sbnChg > 0 ? "naik" : "turun"} ${bpFormat.format(Math.abs(sbnChg))} bps)` : ""} dengan spread terhadap UST 10Y sebesar ${numberFormat.format(spreadVal)} bps. Dinamika ini mencerminkan pergeseran premi risiko investasi obligasi negara.`
                      : "Imbal hasil obligasi negara menunjukkan dinamika volatilitas yang memengaruhi valuasi portofolio surat berharga."}
                  </p>
                  <div className="treasury-pillar-rec-box">
                    <strong className="treasury-rec-label">Rekomendasi Tindakan:</strong>
                    <ul className="treasury-rec-list">
                      <li><strong>Trading Book (FVTPL/FVOCI):</strong> Batasi durasi portofolio pada tenor pendek hingga menengah guna meminimalkan risiko penurunan nilai wajar (<em>mark-to-market</em>).</li>
                      <li><strong>Investment Book (HTM/Amortised Cost):</strong> Manfaatkan momentum lonjakan yield untuk akumulasi selektif pada seri acuan FR/PBS bertenor 5–10 tahun.</li>
                      <li>Pantau jadwal penerbitan dan lelang Surat Berharga Negara dari Kementerian Keuangan untuk penyesuaian kuota penyerapan.</li>
                    </ul>
                  </div>
                </div>

                {/* Pillar 3: Money Market & ALM */}
                <div className="treasury-pillar-card">
                  <div className="treasury-pillar-header">
                    <h4 className="treasury-pillar-title">3. Pasar Uang &amp; Pengelolaan Likuiditas (Money Market &amp; ALM)</h4>
                    <span className="treasury-pillar-badge">Likuiditas Moneter</span>
                  </div>
                  <p className="treasury-pillar-analysis">
                    Suku bunga kebijakan BI Rate berada di {decimalFormat.format(biRateVal)}% dan suku bunga pasar uang antarbank (INDONIA) di {decimalFormat.format(indoniaVal)}%. Likuiditas rupiah perbankan terjaga, namun pengelolaan likuiditas harian menuntut efisiensi biaya dana.
                  </p>
                  <div className="treasury-pillar-rec-box">
                    <strong className="treasury-rec-label">Rekomendasi Tindakan:</strong>
                    <ul className="treasury-rec-list">
                      <li>Tempatkan kelebihan likuiditas harian pada instrumen moneter kontraksi berimbal hasil kompetitif (SRBI, SVBI, dan Term Deposit Valas BI) serta PUAS.</li>
                      <li>Pastikan rasio alat likuid (AL/NCD dan LCR) selalu berada di atas batas pengawasan internal dan regulasi OJK/BI.</li>
                      <li>Koordinasikan penyesuaian suku bunga dana pihak ketiga (DPK) bersama komite ALCO agar biaya dana (<em>Cost of Funds</em>) tetap terkendali.</li>
                    </ul>
                  </div>
                </div>

                {/* Pillar 4: Market Catalyst & Authority Response */}
                <div className="treasury-pillar-card">
                  <div className="treasury-pillar-header">
                    <h4 className="treasury-pillar-title">4. Sentimen Katalis Pasar &amp; Antisipasi Kebijakan</h4>
                    <span className="treasury-pillar-badge">
                      {ihsgChg && Math.abs(ihsgChg) > 2 ? "Volatilitas Ekstrem" : "Sentimen Pasar"}
                    </span>
                  </div>
                  <p className="treasury-pillar-analysis">
                    {ihsgChg && Math.abs(ihsgChg) > 2
                      ? `Pergerakan IHSG yang berfluktuasi tajam (${ihsgChg > 0 ? "+" : ""}${decimalFormat.format(ihsgChg)}%) mencerminkan kekhawatiran pelaku pasar terhadap isu investabilitas dan arus modal asing.`
                      : "Pelaku pasar memantau agenda kebijakan moneter global The Fed serta perkembangan reformasi pasar modal domestik."}
                  </p>
                  <div className="treasury-pillar-rec-box">
                    <strong className="treasury-rec-label">Rekomendasi Tindakan:</strong>
                    <ul className="treasury-rec-list">
                      <li>Antisipasi langkah stabilisasi moneter Bank Indonesia melalui <em>triple intervention</em> (pasar spot, pasar DNDF, dan pasar sekunder SBN) sebagai sinyal batas bawah pasar.</li>
                      <li>Terapkan disiplin batas kerugian (<em>stop loss limit</em>) pada transaksi trading dan tingkatkan koordinasi antar-desk Treasury.</li>
                    </ul>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Practical Impacts from Report */}
          {report.impacts && report.impacts.length > 0 && (
            <div className="treasury-business-impacts">
              <h4 className="treasury-subheading">Dampak Terkait bagi Sektor Riil &amp; Bisnis Nasabah</h4>
              <div className="treasury-impacts-grid">
                {report.impacts.map((item, idx) => (
                  <div key={idx} className="treasury-impact-item">
                    <strong className="treasury-impact-title">{item.title}</strong>
                    <p className="treasury-impact-text">{item.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Bottom Footer Actions */}
          <div className="treasury-panel-footer">
            <span className="treasury-panel-footer-note">Panduan Analisis Pasar • BSI Daily Market Report</span>
            <button
              type="button"
              className="treasury-panel-bottom-close"
              onClick={handleClose}
            >
              <span>Sembunyikan Analisis Treasury</span>
            </button>
          </div>
        </section>
      )}
    </>
  );
}
