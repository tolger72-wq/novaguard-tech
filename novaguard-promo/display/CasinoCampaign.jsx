import { useState, useEffect, useCallback } from "react";

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600;700;900&family=Cinzel+Decorative:wght@700;900&family=EB+Garamond:ital,wght@0,400;0,600&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{--gold:#d4af37;--gold-l:#f5e17a;--gold-d:#8b6d1a;--red:#c41e3a;--red-l:#e8334a;--cyan:#00c8ff;--bg:#05050a;--bg2:#0c0c16;--bg3:#141424;--text:#ede5d0;--dim:#524a40;}
@keyframes shimmer{0%{background-position:-200% center}100%{background-position:200% center}}
@keyframes glow-gold{0%,100%{box-shadow:0 0 14px rgba(212,175,55,.35)}50%{box-shadow:0 0 40px rgba(212,175,55,.9),0 0 80px rgba(212,175,55,.28)}}
@keyframes glow-red{0%,100%{box-shadow:0 0 14px rgba(196,30,58,.4)}50%{box-shadow:0 0 40px rgba(232,51,74,.95),0 0 80px rgba(196,30,58,.32)}}
@keyframes glow-cyan{0%,100%{box-shadow:0 0 10px rgba(0,200,255,.3)}50%{box-shadow:0 0 28px rgba(0,200,255,.8)}}
@keyframes winner-pop{0%{transform:scale(.1) rotate(-15deg);opacity:0}65%{transform:scale(1.06) rotate(2deg);opacity:1}100%{transform:scale(1) rotate(0);opacity:1}}
@keyframes twist-in{0%{transform:scale(.05) rotate(-25deg);opacity:0}60%{transform:scale(1.1) rotate(3deg);opacity:1}100%{transform:scale(1) rotate(0);opacity:1}}
@keyframes confetti-drop{0%{transform:translateY(-30px) rotate(0);opacity:1}100%{transform:translateY(110vh) rotate(var(--r));opacity:0}}
@keyframes slide-in{0%{transform:translateX(100%)}100%{transform:translateX(0)}}
@keyframes fade-up{0%{opacity:0;transform:translateY(16px)}100%{opacity:1;transform:translateY(0)}}
@keyframes flash{0%,100%{opacity:.55}50%{opacity:1}}
@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
@keyframes bg-breathe{0%,100%{background:rgba(196,30,58,.04)}50%{background:rgba(196,30,58,.1)}}
@keyframes hunt-pulse{0%,100%{box-shadow:0 0 6px rgba(212,175,55,.2)}50%{box-shadow:0 0 20px rgba(212,175,55,.5)}}
@keyframes mystery-pulse{0%,100%{opacity:.35;transform:scale(1)}50%{opacity:1;transform:scale(1.05)}}
@keyframes prize-flip{0%{transform:rotateY(90deg);opacity:0}100%{transform:rotateY(0);opacity:1}}
.shimmer{background:linear-gradient(90deg,var(--gold-d) 0%,var(--gold-l) 40%,var(--gold) 60%,var(--gold-d) 100%);background-size:200% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:shimmer 3s linear infinite}
.winner-pop{animation:winner-pop .7s cubic-bezier(.34,1.56,.64,1) forwards}
.twist-in{animation:twist-in .8s cubic-bezier(.34,1.56,.64,1) forwards}
.fade-up{animation:fade-up .4s ease both}
.flash-anim{animation:flash .13s ease-in-out infinite}
.float-anim{animation:float 3.5s ease-in-out infinite}
.glow-gold{animation:glow-gold 2s ease-in-out infinite}
.glow-red{animation:glow-red 1.8s ease-in-out infinite}
.glow-cyan{animation:glow-cyan 2s ease-in-out infinite}
.hunt-pulse{animation:hunt-pulse 2.8s ease-in-out infinite}
.mystery-pulse{animation:mystery-pulse 2s ease-in-out infinite}
.prize-flip{animation:prize-flip .6s cubic-bezier(.34,1.56,.64,1) forwards}
`;

const CURRENCIES = [
  { symbol:"₺", code:"TL",  name:"Türk Lirası", prefix:false },
  { symbol:"€", code:"EUR", name:"Euro",         prefix:true  },
  { symbol:"$", code:"USD", name:"Dolar",        prefix:true  },
  { symbol:"₾", code:"GEL", name:"Gürcü Larisi",prefix:false },
  { symbol:"£", code:"GBP", name:"Sterlin",      prefix:true  },
];

const FINAL_PRIZES = [
  { key:"cash",  icon:"💰", tr:"NAKİT ÖDÜL",     en:"CASH PRIZE"           },
  { key:"car",   icon:"🚗", tr:"MERCEDES S-CLASS",en:"MERCEDES S-CLASS"    },
  { key:"house", icon:"🏠", tr:"2+1 LÜKS DAİRE",  en:"2+1 LUXURY APARTMENT"},
];

const MOCK = [
  {id:"KRT-001",name:"Ahmet Yılmaz",  visits:22,hours:48, tickets:110},
  {id:"KRT-002",name:"Fatma Kaya",    visits:15,hours:32, tickets:84 },
  {id:"KRT-003",name:"Mehmet Demir",  visits:12,hours:28, tickets:68 },
  {id:"KRT-004",name:"Ayşe Şahin",    visits:8, hours:18, tickets:44 },
  {id:"KRT-005",name:"Mustafa Çelik", visits:6, hours:14, tickets:32 },
  {id:"KRT-006",name:"Zeynep Arslan", visits:19,hours:42, tickets:96 },
  {id:"KRT-007",name:"Hasan Koç",     visits:26,hours:58, tickets:138},
  {id:"KRT-008",name:"Elif Yıldız",   visits:5, hours:10, tickets:26 },
  {id:"KRT-009",name:"İbrahim Öztürk",visits:3, hours:6,  tickets:14 },
  {id:"KRT-010",name:"Hatice Aydın",  visits:11,hours:24, tickets:58 },
];

const T = {
  tr:{
    brand:"NOVAGUARD", title:"ŞAMPİYONLUK SERİSİ",
    weekly:"HAFTALIK", quarterly:"3 AYLIK", final:"YIL SONU FİNALİ",
    weeklyPrize:"Bu Haftanın Ödülü", growthNote:"Her haftada büyür",
    quarterlyPrize:"Çeyrek Ödülü",
    finalNight:"13 OCAK GECESİ", finalSub:"Eski Gürcü Yılbaşı",
    prizeReveal:"ÖDÜL ÇEKİLİŞİ", prizeRevealSub:"Büyük ödül türü belirleniyor",
    mystery:"?", revealBtn:"ÖDÜLÜ ÇEKEL!",
    spin:"ÇEKİLİŞİ BAŞLAT", spinning:"ÇEKİLİYOR...",
    winner:"KAZANAN", grandWinner:"YIL'IN BÜYÜK KAZANANI", congrats:"TEBRİKLER!",
    nextPrize:"Bir sonraki aşama ödülüne katılamaz", finalSee:"13 Ocak'ta görüşürüz!",
    huntMsg:"BÜYÜK ÖDÜL BEKLIYOR",
    operator:"OPERATÖR", loadApi:"API'DEN YÜKLE", loading:"Yükleniyor...",
    reset:"SIFIRLA", tickets:"Bilet", eligible:"uygun",
    iron:"⚡ DEMİR", superloyal:"🔥 SÜPER", regular:"★ DÜZ.",
    semireg:"◆ YARI", standard:"· STD",
    confirm:"ONAYLA →", overview:"KAMPANYA", drawMode:"ÇEKİLİŞ", finalMode:"FİNAL",
    noPart:"Katılımcı yok — yükle", participants:"Katılımcı",
    currentWeek:"Hafta", currentQ:"Çeyrek", poolTotal:"Bilet",
    currency:"Para Birimi", prizes:"Ödül Miktarları",
    wkBase:"Haftalık Başlangıç", wkGrowth:"Haftalık Büyüme",
    finalCashLabel:"Final Nakit Ödülü",
    campaignState:"Kampanya Durumu", currentPool:"Mevcut Haftalık Havuz",
    excluded:"Havuz Dışı",
  },
  en:{
    brand:"NOVAGUARD", title:"CHAMPIONSHIP SERIES",
    weekly:"WEEKLY", quarterly:"QUARTERLY", final:"YEAR-END FINAL",
    weeklyPrize:"This Week's Prize", growthNote:"Grows each week",
    quarterlyPrize:"Quarterly Prize",
    finalNight:"JANUARY 13th", finalSub:"Old Georgian New Year",
    prizeReveal:"PRIZE DRAW", prizeRevealSub:"Grand prize type being decided",
    mystery:"?", revealBtn:"DRAW THE PRIZE!",
    spin:"START DRAW", spinning:"DRAWING...",
    winner:"WINNER", grandWinner:"YEAR'S GRAND WINNER", congrats:"CONGRATULATIONS!",
    nextPrize:"Cannot win the next stage prize", finalSee:"See you on January 13th!",
    huntMsg:"HUNTING BIG PRIZE",
    operator:"OPERATOR", loadApi:"LOAD FROM API", loading:"Loading...",
    reset:"RESET", tickets:"Tickets", eligible:"eligible",
    iron:"⚡ IRON", superloyal:"🔥 SUPER", regular:"★ REG.",
    semireg:"◆ SEMI", standard:"· STD",
    confirm:"CONFIRM →", overview:"CAMPAIGN", drawMode:"DRAW", finalMode:"FINAL",
    noPart:"No participants — load", participants:"Participants",
    currentWeek:"Week", currentQ:"Quarter", poolTotal:"Tickets",
    currency:"Currency", prizes:"Prize Amounts",
    wkBase:"Weekly Base", wkGrowth:"Weekly Growth",
    finalCashLabel:"Final Cash Prize",
    campaignState:"Campaign State", currentPool:"Current Weekly Pool",
    excluded:"Excluded",
  },
};

// ── HELPERS ───────────────────────────────────────────────────────────────────
const getWeight = (p) => {
  const s = p.visits + Math.floor(p.hours / 5);
  return s >= 30 ? 5 : s >= 22 ? 4 : s >= 15 ? 3 : s >= 8 ? 2 : 1;
};

const getMeta = (w, t) => {
  if (w >= 5) return { label:t.iron,      color:"#e040fb", bg:"rgba(192,64,232,.1)"  };
  if (w >= 4) return { label:t.superloyal,color:"#ff6d00", bg:"rgba(255,109,0,.09)"  };
  if (w >= 3) return { label:t.regular,   color:"#00c8ff", bg:"rgba(0,200,255,.07)"  };
  if (w >= 2) return { label:t.semireg,   color:"#d4af37", bg:"rgba(212,175,55,.07)" };
  return              { label:t.standard, color:"#524a40", bg:"rgba(82,74,64,.05)"   };
};

// ── CONFETTI ──────────────────────────────────────────────────────────────────
function Confetti({ show }) {
  const p = Array.from({length:110}, (_,i) => ({
    id:i, x:Math.random()*100,
    c:["#d4af37","#f5e17a","#c41e3a","#fff","#00c8ff","#c040e8","#ff6d00"][i%7],
    s:5+Math.random()*9, delay:Math.random()*3.5, dur:3+Math.random()*2.5,
    r:`${Math.random()*900-450}deg`, rect:Math.random()>.4,
  }));
  if (!show) return null;
  return (
    <div style={{position:"fixed",inset:0,pointerEvents:"none",zIndex:300,overflow:"hidden"}}>
      {p.map(x => (
        <div key={x.id} style={{position:"absolute",left:`${x.x}%`,top:-20,
          width:x.s, height:x.rect?x.s*1.8:x.s, borderRadius:x.rect?2:"50%",
          background:x.c, "--r":x.r,
          animation:`confetti-drop ${x.dur}s ${x.delay}s linear forwards`}}/>
      ))}
    </div>
  );
}

// ── COUNTDOWN ─────────────────────────────────────────────────────────────────
function Countdown({ t }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(i); }, []);
  const target = new Date(now.getFullYear() + (now.getMonth() >= 1 ? 1 : 0), 0, 13, 20, 0, 0);
  const diff = Math.max(0, target - now);
  const days = Math.floor(diff / 864e5);
  const hrs  = Math.floor((diff % 864e5) / 36e5);
  const mins = Math.floor((diff % 36e5) / 6e4);
  const secs = Math.floor((diff % 6e4) / 1e3);
  const pad  = n => String(n).padStart(2, "0");
  return (
    <div style={{textAlign:"center",padding:"8px 0"}}>
      <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:4,color:"rgba(232,51,74,.5)",marginBottom:6}}>
        {t.finalNight}
      </div>
      <div style={{display:"flex",gap:14,justifyContent:"center",alignItems:"baseline"}}>
        {[["Gün",days],["Sa",hrs],["Dk",mins],["Sn",secs]].map(([l,v]) => (
          <div key={l} style={{textAlign:"center"}}>
            <div style={{fontFamily:"'Cinzel',serif",fontSize:22,fontWeight:700,color:"var(--red-l)",lineHeight:1}}>{pad(v)}</div>
            <div style={{fontFamily:"'Cinzel',serif",fontSize:7,color:"rgba(232,51,74,.4)",letterSpacing:2}}>{l}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── PRIZE PYRAMID ─────────────────────────────────────────────────────────────
function PrizePyramid({ weeklyPool, weekNum, quarterIdx, quarterlyWinners, weeklyExcluded, lang, t, fmt, cfg }) {
  return (
    <div style={{display:"flex",flexDirection:"column",gap:8,width:"100%"}}>

      {/* FINAL ROW */}
      <div className="glow-red" style={{background:"linear-gradient(135deg,rgba(139,26,46,.18),rgba(196,30,58,.08),rgba(139,26,46,.18))",border:"2px solid rgba(232,51,74,.5)",padding:"13px 22px",display:"flex",alignItems:"center",justifyContent:"space-between",position:"relative",overflow:"hidden",animation:"bg-breathe 4s ease-in-out infinite"}}>
        <div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:4,color:"rgba(232,51,74,.65)",marginBottom:4}}>{t.finalNight} — {t.finalSub}</div>
          <div style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:11,color:"var(--red-l)",letterSpacing:3}}>{t.final}</div>
        </div>
        <div style={{display:"flex",gap:16}}>
          {FINAL_PRIZES.map(p => (
            <div key={p.key} style={{textAlign:"center"}}>
              <div style={{fontSize:20,marginBottom:3}}>{p.icon}</div>
              <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:"var(--red-l)",letterSpacing:1}}>
                {p.key === "cash" ? fmt(cfg.finalCash) : p[lang].split(" ").slice(0,2).join(" ")}
              </div>
            </div>
          ))}
        </div>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:11,letterSpacing:4,color:"var(--red-l)",opacity:.5}}>13.01</div>
      </div>

      {/* QUARTERLY ROW */}
      <div className="glow-cyan" style={{background:"rgba(0,160,200,.07)",border:"1px solid rgba(0,200,255,.28)",padding:"11px 22px",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"rgba(0,200,255,.55)",marginBottom:4}}>{t.quarterly} · {t.currentQ} {quarterIdx+1}/4</div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:11,color:"var(--cyan)",letterSpacing:2}}>{t.quarterlyPrize}</div>
        </div>
        <div>
          {cfg.quarterly.map((q, i) => (
            <span key={i} style={{fontFamily:"'Cinzel',serif",fontSize:i===quarterIdx?16:10,color:i===quarterIdx?"var(--cyan)":"rgba(0,200,255,.22)",marginLeft:12,fontWeight:i===quarterIdx?700:400,textDecoration:quarterlyWinners[i]?"line-through":undefined}}>
              {i===quarterIdx?"→ ":""}{fmt(q)}
            </span>
          ))}
        </div>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:9,color:"rgba(0,200,255,.4)"}}>{quarterlyWinners.filter(Boolean).length} kazanıldı</div>
      </div>

      {/* WEEKLY ROW */}
      <div className="glow-gold" style={{background:"rgba(180,140,20,.07)",border:"1px solid rgba(212,175,55,.32)",padding:"11px 22px",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"rgba(212,175,55,.55)",marginBottom:4}}>{t.weekly} · {t.currentWeek} {weekNum}</div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:10,color:"var(--gold)",letterSpacing:2}}>{t.weeklyPrize}</div>
        </div>
        <div>
          <div style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:24,color:"var(--gold-l)",letterSpacing:2,textAlign:"right"}}>{fmt(weeklyPool)}</div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:2,color:"rgba(212,175,55,.38)",textAlign:"right",marginTop:3}}>{t.growthNote} +{fmt(cfg.weeklyGrowth)}</div>
        </div>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:9,color:"rgba(212,175,55,.4)"}}>{weeklyExcluded.length} dışında</div>
      </div>
    </div>
  );
}

// ── PLAYER ROW ────────────────────────────────────────────────────────────────
function PlayerRow({ player, mode, weeklyExcluded, quarterlyExcluded, t, isWinner, isDrum }) {
  const isWkEx = weeklyExcluded.includes(player.id);
  const isQEx  = quarterlyExcluded.includes(player.id);
  const ineligible = (mode === "final" && isQEx) || (mode !== "final" && (isWkEx || isQEx));
  const hunting = !isWkEx && !isQEx;
  const w = getWeight(player);
  const meta = getMeta(w, t);
  return (
    <div className={isWinner ? "glow-gold" : hunting && !ineligible ? "hunt-pulse" : ""}
      style={{padding:"8px 11px",background:isWinner?"rgba(212,175,55,.13)":ineligible?"rgba(12,10,18,.7)":"var(--bg2)",border:`1px solid ${isWinner?"var(--gold)":ineligible?"rgba(35,30,24,.5)":"rgba(212,175,55,.09)"}`,opacity:ineligible?.38:1,transition:"all .3s",animation:isDrum?"flash-anim":undefined}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:6}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:10,color:isWinner?"var(--gold-l)":"var(--text)",marginBottom:2,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{player.name}</div>
          <div style={{display:"flex",gap:6}}>
            <span style={{fontFamily:"'Cinzel',serif",fontSize:7,color:"var(--dim)"}}>{player.id}</span>
            {isWkEx && !isQEx && <span style={{fontFamily:"'Cinzel',serif",fontSize:7,color:"rgba(212,175,55,.3)"}}>Hf dışı</span>}
            {isQEx  && <span style={{fontFamily:"'Cinzel',serif",fontSize:7,color:"rgba(0,200,255,.35)"}}>Çyr dışı</span>}
          </div>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:6,flexShrink:0}}>
          <span style={{fontFamily:"'Cinzel',serif",fontSize:10,fontWeight:700,color:"var(--gold)",minWidth:28,textAlign:"right"}}>{player.tickets}</span>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:7,letterSpacing:1,padding:"2px 6px",border:`1px solid ${meta.color}`,color:meta.color,background:meta.bg}}>{meta.label} ×{w}</div>
        </div>
      </div>
      <div style={{display:"flex",gap:3,marginTop:5,alignItems:"center"}}>
        {Array.from({length:5}, (_,i) => (
          <div key={i} style={{width:12,height:3,borderRadius:2,background:i<w?meta.color:"rgba(60,52,42,.2)"}}/>
        ))}
        <span style={{fontFamily:"'Cinzel',serif",fontSize:7,color:"var(--dim)",marginLeft:3}}>×{w}</span>
      </div>
    </div>
  );
}

// ── TWIST OVERLAY ─────────────────────────────────────────────────────────────
function TwistOverlay({ show, winner, mode, weeklyPool, quarterIdx, grandPrizeType, lang, t, onDismiss, fmt, cfg }) {
  if (!show || !winner) return null;
  const isFinal = mode === "final";
  const isQ     = mode === "quarterly";
  const prize   = isFinal ? (FINAL_PRIZES.find(p => p.key === grandPrizeType) || FINAL_PRIZES[0]) : null;
  const prizeText = isFinal
    ? (prize?.key === "cash" ? fmt(cfg.finalCash) : prize?.[lang] || "")
    : isQ ? fmt(cfg.quarterly[quarterIdx] || 0) : fmt(weeklyPool);
  const prizeIcon  = isFinal ? prize?.icon : isQ ? "🏆" : "🎰";
  const stageColor = isFinal ? "var(--red-l)" : isQ ? "var(--cyan)" : "var(--gold)";
  return (
    <div style={{position:"fixed",inset:0,zIndex:200,display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",background:"rgba(5,5,10,.95)",backdropFilter:"blur(12px)"}}>
      <div className="winner-pop" style={{textAlign:"center",marginBottom:isFinal?20:36}}>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:5,color:stageColor,marginBottom:12}}>{isFinal?t.grandWinner:t.winner}</div>
        <div style={{fontSize:isFinal?52:40,marginBottom:10}}>{prizeIcon}</div>
        <div className={isFinal?"glow-red":isQ?"glow-cyan":"glow-gold"} style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:isFinal?44:32,fontWeight:900,color:isFinal?"var(--red-l)":isQ?"var(--cyan)":"var(--gold-l)",padding:"14px 32px",border:`2px solid ${stageColor}`,marginBottom:12}}>{winner.name}</div>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:16,color:stageColor,letterSpacing:3,marginBottom:6}}>{prizeText}</div>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:9,color:"var(--dim)"}}>{winner.id} · {winner.tickets} {t.tickets}</div>
      </div>
      {!isFinal && (
        <div className="twist-in" style={{textAlign:"center",borderTop:"1px solid rgba(212,175,55,.1)",paddingTop:24,maxWidth:480,width:"100%"}}>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:10,letterSpacing:3,color:"rgba(82,74,64,.8)",marginBottom:7}}>
            {isQ ? "Yıl sonu finaline katılamazsınız." : t.nextPrize}
          </div>
          <div style={{fontFamily:"'Cinzel',serif",fontSize:11,letterSpacing:3,color:"rgba(212,175,55,.4)"}}>{t.finalSee}</div>
        </div>
      )}
      {isFinal && <div className="fade-up float-anim" style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:18,letterSpacing:6,color:"var(--red-l)"}}>{t.congrats}</div>}
      <button onClick={onDismiss} style={{marginTop:36,fontFamily:"'Cinzel',serif",fontSize:10,letterSpacing:4,padding:"12px 44px",background:"transparent",border:`1px solid ${stageColor}`,color:stageColor,cursor:"pointer"}}>
        {isFinal ? "✦ ŞAMPİYON" : "DEVAM →"}
      </button>
    </div>
  );
}

// ── FINAL PRIZE REVEAL ────────────────────────────────────────────────────────
function FinalPrizeReveal({ revealed, selected, onReveal, lang, t, cfg, fmt }) {
  const [spinning, setSpinning] = useState(false);
  const [cur, setCur]           = useState(null);

  const doReveal = () => {
    if (spinning) return;
    setSpinning(true);
    let count = 0;
    const iv = setInterval(() => {
      setCur(FINAL_PRIZES[count % 3].key);
      count++;
      if (count >= 20) {
        clearInterval(iv);
        const final = FINAL_PRIZES[Math.floor(Math.random() * 3)];
        setCur(final.key);
        setSpinning(false);
        onReveal(final.key);
      }
    }, 180);
  };

  const show = cur || selected;
  return (
    <div style={{background:"rgba(139,26,46,.1)",border:"2px solid rgba(232,51,74,.32)",padding:"20px 24px",marginBottom:14,textAlign:"center",animation:"bg-breathe 4s ease-in-out infinite"}}>
      <div style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:4,color:"rgba(232,51,74,.55)",marginBottom:8}}>{t.prizeReveal}</div>
      <div style={{fontFamily:"'Cinzel',serif",fontSize:9,color:"rgba(232,51,74,.38)",marginBottom:14,letterSpacing:2}}>{t.prizeRevealSub}</div>
      {!revealed && !spinning ? (
        <button onClick={doReveal} className="mystery-pulse" style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:20,letterSpacing:4,padding:"16px 48px",background:"rgba(196,30,58,.07)",border:"2px solid rgba(232,51,74,.4)",color:"rgba(232,51,74,.55)",cursor:"pointer"}}>
          {t.mystery} &nbsp; {t.mystery} &nbsp; {t.mystery}
          <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,marginTop:8,color:"rgba(232,51,74,.38)"}}>{t.revealBtn}</div>
        </button>
      ) : (
        <div style={{display:"flex",justifyContent:"center",gap:20}}>
          {FINAL_PRIZES.map(p => (
            <div key={p.key} className={p.key === show ? "prize-flip" : ""} style={{textAlign:"center",padding:"12px 16px",background:p.key===show?"rgba(196,30,58,.15)":"rgba(20,16,24,.5)",border:`2px solid ${p.key===show?"var(--red-l)":"rgba(44,36,44,.3)"}`,transition:"all .2s",transform:p.key===show?"scale(1.06)":"scale(1)"}}>
              <div style={{fontSize:p.key===show?34:22,marginBottom:6}}>{p.icon}</div>
              <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:p.key===show?"var(--red-l)":"rgba(90,70,80,.45)",letterSpacing:1}}>
                {p.key==="cash" ? fmt(cfg.finalCash) : p[lang]}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── HUNT TICKER ───────────────────────────────────────────────────────────────
function HuntTicker({ players, weeklyExcluded, quarterlyExcluded, t }) {
  const hunting = players.filter(p => !weeklyExcluded.includes(p.id) && !quarterlyExcluded.includes(p.id));
  if (!hunting.length) return null;
  const msg = hunting.map(p => `${p.name}  (${p.tickets} ${t.tickets})  ·  `).join("").repeat(3);
  return (
    <div style={{position:"fixed",bottom:0,left:0,right:0,zIndex:10,background:"rgba(5,5,10,.96)",borderTop:"1px solid rgba(212,175,55,.08)",padding:"8px 0"}}>
      <div style={{display:"flex",alignItems:"center",paddingLeft:14,gap:12}}>
        <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--gold)",whiteSpace:"nowrap",flexShrink:0}}>🎯 {t.huntMsg}</div>
        <div style={{flex:1,overflow:"hidden",maskImage:"linear-gradient(90deg,transparent,black 50px,black calc(100% - 50px),transparent)"}}>
          <div className="shimmer" style={{fontFamily:"'Cinzel',serif",fontSize:8,whiteSpace:"nowrap",letterSpacing:2,
            background:"linear-gradient(90deg,var(--gold-d),var(--gold-l),var(--gold),var(--gold-d))",
            backgroundSize:"200% auto",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",animation:"shimmer 12s linear infinite"}}>
            {msg}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── MAIN ──────────────────────────────────────────────────────────────────────
export default function CasinoCampaign() {
  const [lang, setLang]         = useState("tr");
  const [view, setView]         = useState("overview");
  const [mode, setMode]         = useState("weekly");
  const [players, setPlayers]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [showPanel, setShowPanel] = useState(false);

  // Currency & prize config
  const [currency, setCurrency] = useState(CURRENCIES[0]);
  const [cfg, setCfg]           = useState({ weeklyBase:500, weeklyGrowth:200, quarterly:[25000,50000,100000], finalCash:500000 });
  const fmt = n => currency.prefix ? `${currency.symbol} ${Number(n).toLocaleString()}` : `${Number(n).toLocaleString()} ${currency.symbol}`;

  // Campaign state
  const [weekNum, setWeekNum]           = useState(23);
  const [weeklyPool, setWeeklyPool]     = useState(4900);
  const [quarterIdx, setQuarterIdx]     = useState(1);
  const [weeklyExcluded, setWeeklyExcluded]     = useState([]);
  const [quarterlyExcluded, setQuarterlyExcluded] = useState([]);
  const [quarterlyWinners, setQuarterlyWinners]   = useState([null,null,null]);

  // Draw state
  const [spinning, setSpinning]       = useState(false);
  const [drumIdx, setDrumIdx]         = useState(0);
  const [showWinner, setShowWinner]   = useState(false);
  const [pendingWinner, setPendingWinner] = useState(null);
  const [showTwist, setShowTwist]     = useState(false);
  const [confetti, setConfetti]       = useState(false);
  const [grandPrizeType, setGrandPrizeType]     = useState(null);
  const [grandPrizeRevealed, setGrandPrizeRevealed] = useState(false);

  const t = T[lang];

  const getEligible = useCallback(() => {
    if (mode === "final") return players.filter(p => !quarterlyExcluded.includes(p.id));
    return players.filter(p => !weeklyExcluded.includes(p.id) && !quarterlyExcluded.includes(p.id));
  }, [players, mode, weeklyExcluded, quarterlyExcluded]);

  const eligible = getEligible();
  const pool     = eligible.flatMap(p => Array(getWeight(p)).fill(p));
  const drumPlayer = pool[drumIdx % Math.max(pool.length, 1)];

  const loadPlayers = async () => {
    setLoading(true);
    await new Promise(r => setTimeout(r, 1100));
    setPlayers(MOCK);
    setLoading(false);
  };

  const startRaffle = useCallback(() => {
    if (!pool.length || spinning) return;
    const actual = pool[Math.floor(Math.random() * pool.length)];
    setSpinning(true); setShowWinner(false); setPendingWinner(null); setConfetti(false);
    let count = 0;
    const fast = setInterval(() => {
      setDrumIdx(i => (i + 1) % pool.length);
      count++;
      if (count >= 65) {
        clearInterval(fast);
        let delay = 80, slow = 0;
        const tick = () => {
          setDrumIdx(i => (i + 1) % pool.length);
          slow++; delay = Math.min(delay * 1.38, 700);
          if (slow < 12) setTimeout(tick, delay);
          else {
            const wIdx = pool.findIndex(p => p.id === actual.id);
            setDrumIdx(wIdx >= 0 ? wIdx : 0);
            setSpinning(false);
            setTimeout(() => {
              setShowWinner(true); setPendingWinner(actual);
              if (mode === "final") { setConfetti(true); setTimeout(() => setConfetti(false), 8000); }
            }, 400);
          }
        };
        setTimeout(tick, delay);
      }
    }, 70);
  }, [pool, spinning, mode]);

  const confirmWinner = () => {
    if (!pendingWinner) return;
    if (mode === "weekly") {
      setWeeklyExcluded(p => [...p, pendingWinner.id]);
      setWeeklyPool(cfg.weeklyBase + (weekNum + 1) * cfg.weeklyGrowth);
    } else if (mode === "quarterly") {
      setQuarterlyExcluded(p => [...p, pendingWinner.id]);
      const qw = [...quarterlyWinners]; qw[quarterIdx] = pendingWinner; setQuarterlyWinners(qw);
    }
    setShowWinner(false); setShowTwist(true);
  };

  const dismissTwist = () => {
    setShowTwist(false); setPendingWinner(null);
    if (mode === "weekly") setWeekNum(w => w + 1);
  };

  const modeColor = mode === "final" ? "var(--red-l)" : mode === "quarterly" ? "var(--cyan)" : "var(--gold)";
  const modePrize = mode === "final"
    ? (grandPrizeType ? (FINAL_PRIZES.find(p => p.key === grandPrizeType)?.[lang] === "NAKİT ÖDÜL" || FINAL_PRIZES.find(p => p.key === grandPrizeType)?.key === "cash" ? fmt(cfg.finalCash) : FINAL_PRIZES.find(p => p.key === grandPrizeType)?.[lang] || "") : "???")
    : mode === "quarterly" ? fmt(cfg.quarterly[quarterIdx] || 0) : fmt(weeklyPool);

  const lbl = (style, ch) => (
    <label style={{fontFamily:"'Cinzel',serif",fontSize:7,color:ch||"var(--dim)",display:"block",marginBottom:3}}>{style}</label>
  );

  const inp = (val, onChange, border) => (
    <input type="number" value={val} onChange={onChange}
      style={{width:"100%",background:"var(--bg3)",border:`1px solid ${border||"rgba(212,175,55,.15)"}`,color:"var(--text)",padding:"6px 8px",fontFamily:"'Cinzel',serif",fontSize:11,outline:"none",marginBottom:7}}/>
  );

  return (
    <div style={{fontFamily:"'EB Garamond',serif",background:"var(--bg)",minHeight:"100vh",color:"var(--text)",position:"relative",overflow:"hidden",paddingBottom:50}}>
      <style>{CSS}</style>
      <div style={{position:"fixed",inset:0,backgroundImage:"repeating-linear-gradient(45deg,transparent,transparent 44px,rgba(212,175,55,.009) 44px,rgba(212,175,55,.009) 45px),repeating-linear-gradient(-45deg,transparent,transparent 44px,rgba(212,175,55,.009) 44px,rgba(212,175,55,.009) 45px)",pointerEvents:"none",zIndex:0}}/>
      <Confetti show={confetti}/>
      <TwistOverlay show={showTwist} winner={pendingWinner} mode={mode} weeklyPool={weeklyPool}
        quarterIdx={quarterIdx} grandPrizeType={grandPrizeType} lang={lang} t={t}
        onDismiss={dismissTwist} fmt={fmt} cfg={cfg}/>

      {/* HEADER */}
      <header style={{position:"relative",zIndex:10,display:"flex",alignItems:"center",justifyContent:"space-between",padding:"13px 22px",borderBottom:"1px solid rgba(212,175,55,.09)",background:"rgba(5,5,10,.95)",backdropFilter:"blur(12px)"}}>
        <div>
          <div style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:9,letterSpacing:7,color:"var(--gold)",marginBottom:3}}>{t.brand}</div>
          <div className="shimmer" style={{fontFamily:"'Cinzel',serif",fontSize:17,fontWeight:700,letterSpacing:5}}>{t.title}</div>
        </div>
        <div style={{display:"flex",gap:6}}>
          {[["overview",t.overview],["draw",t.drawMode],["final",t.finalMode]].map(([v,lbl2]) => (
            <button key={v} onClick={() => { setView(v); if(v==="final") setMode("final"); else if(mode==="final") setMode("weekly"); }}
              style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:2,padding:"8px 16px",cursor:"pointer",background:view===v?"rgba(212,175,55,.1)":"transparent",border:`1px solid ${view===v?(v==="final"?"var(--red-l)":"var(--gold)"):"rgba(212,175,55,.18)"}`,color:view===v?(v==="final"?"var(--red-l)":"var(--gold)"):"rgba(212,175,55,.35)"}}>
              {lbl2}
            </button>
          ))}
        </div>
        <div style={{display:"flex",gap:10}}>
          <button onClick={() => setLang(l => l==="tr"?"en":"tr")} style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:3,padding:"7px 12px",background:"transparent",border:"1px solid rgba(212,175,55,.2)",color:"rgba(212,175,55,.5)",cursor:"pointer"}}>{lang==="tr"?"EN":"TR"}</button>
          <button onClick={() => setShowPanel(v => !v)} style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:3,padding:"7px 14px",background:"rgba(180,30,50,.09)",border:"1px solid rgba(180,30,50,.28)",color:"rgba(220,60,80,.65)",cursor:"pointer"}}>{t.operator}</button>
        </div>
      </header>

      <main style={{position:"relative",zIndex:5,padding:"18px 22px 56px"}}>

        {/* ── OVERVIEW ─────────────────────────────────────────────── */}
        {view==="overview" && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 280px",gap:18}}>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <PrizePyramid weeklyPool={weeklyPool} weekNum={weekNum} quarterIdx={quarterIdx}
                quarterlyWinners={quarterlyWinners} weeklyExcluded={weeklyExcluded}
                lang={lang} t={t} fmt={fmt} cfg={cfg}/>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:10}}>
                {[
                  ["draw","weekly","Haftalık Çekiliş","🎰",fmt(weeklyPool),`${eligible.length} ${t.eligible}`],
                  ["draw","quarterly","3 Aylık Çekiliş","🏆",fmt(cfg.quarterly[quarterIdx]||0),`${players.filter(p=>!weeklyExcluded.includes(p.id)&&!quarterlyExcluded.includes(p.id)).length} ${t.eligible}`],
                  ["final","final","13 Ocak Finali","👑","???",`${players.filter(p=>!quarterlyExcluded.includes(p.id)).length} ${t.eligible}`],
                ].map(([v,m,label,icon,prize,pool2]) => (
                  <div key={m} onClick={() => { setMode(m); setView(v); }}
                    style={{padding:"16px",background:"var(--bg2)",border:`1px solid rgba(${m==="final"?"196,30,58":m==="quarterly"?"0,160,200":"180,140,20"},.2)`,cursor:"pointer"}}>
                    <div style={{fontSize:22,marginBottom:8}}>{icon}</div>
                    <div style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:2,color:"var(--dim)",marginBottom:5}}>{label}</div>
                    <div style={{fontFamily:"'Cinzel',serif",fontSize:16,color:"var(--gold)",marginBottom:4}}>{prize}</div>
                    <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:"var(--dim)",letterSpacing:1}}>{pool2}</div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:10}}>
              <Countdown t={t}/>
              {players.length === 0 ? (
                <button onClick={loadPlayers} style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:3,padding:"10px",background:"rgba(212,175,55,.08)",border:"1px solid rgba(212,175,55,.22)",color:"var(--gold)",cursor:"pointer"}}>{loading?t.loading:t.loadApi}</button>
              ) : (
                <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)"}}>{players.length} {t.participants}</div>
              )}
              <div style={{display:"flex",flexDirection:"column",gap:5,maxHeight:380,overflowY:"auto"}}>
                {[...players].sort((a,b)=>b.tickets-a.tickets).map(p => (
                  <PlayerRow key={p.id} player={p} mode={mode} weeklyExcluded={weeklyExcluded}
                    quarterlyExcluded={quarterlyExcluded} t={t} isWinner={false} isDrum={false}/>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── DRAW ─────────────────────────────────────────────────── */}
        {view==="draw" && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 270px",gap:18}}>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{display:"flex",gap:8}}>
                {[["weekly",t.weekly,"var(--gold)"],["quarterly",t.quarterly,"var(--cyan)"]].map(([m,lbl2,c]) => (
                  <button key={m} onClick={() => setMode(m)}
                    style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:2,padding:"9px 20px",cursor:"pointer",background:mode===m?`rgba(${m==="quarterly"?"0,160,200":"180,140,20"},.1)`:"transparent",border:`1px solid ${mode===m?c:"rgba(212,175,55,.14)"}`,color:mode===m?c:"var(--dim)"}}>
                    {lbl2}
                  </button>
                ))}
              </div>
              <div style={{padding:"12px 18px",background:"var(--bg2)",border:`1px solid rgba(${mode==="quarterly"?"0,160,200":"180,140,20"},.2)`,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
                <div>
                  <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)",marginBottom:5}}>{mode==="quarterly"?t.quarterlyPrize:t.weeklyPrize}</div>
                  <div style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:22,color:modeColor,letterSpacing:2}}>{modePrize}</div>
                  {mode==="weekly" && <div style={{fontFamily:"'Cinzel',serif",fontSize:7,color:"rgba(212,175,55,.38)",letterSpacing:2,marginTop:3}}>{t.growthNote}</div>}
                </div>
                <div style={{textAlign:"right"}}>
                  <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:"var(--dim)"}}>{pool.length} {t.poolTotal}</div>
                  <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:"var(--dim)",marginTop:3}}>{eligible.length} {t.eligible}</div>
                </div>
              </div>
              <div style={{height:190,background:"var(--bg2)",border:`1px solid ${showWinner?modeColor:"rgba(212,175,55,.13)"}`,display:"flex",alignItems:"center",justifyContent:"center",position:"relative",transition:"border-color .4s"}}>
                {[[0,null,null,0],[0,0,null,null],[null,null,0,0],[null,0,0,null]].map(([t2,r2,b2,l2],i) => (
                  <div key={i} style={{position:"absolute",top:t2!=null?8:undefined,bottom:b2!=null?8:undefined,left:l2!=null?8:undefined,right:r2!=null?8:undefined,width:12,height:12,borderTop:t2!=null?"1px solid rgba(212,175,55,.3)":undefined,borderBottom:b2!=null?"1px solid rgba(212,175,55,.3)":undefined,borderLeft:l2!=null?"1px solid rgba(212,175,55,.3)":undefined,borderRight:r2!=null?"1px solid rgba(212,175,55,.3)":undefined}}/>
                ))}
                {players.length===0 ? (
                  <div style={{fontFamily:"'Cinzel',serif",fontSize:11,letterSpacing:2,color:"var(--dim)"}}>{t.noPart}</div>
                ) : showWinner && pendingWinner ? (
                  <div className="winner-pop" style={{textAlign:"center",padding:20}}>
                    <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:5,color:modeColor,marginBottom:10}}>{t.winner}</div>
                    <div className={mode==="quarterly"?"glow-cyan":"glow-gold"} style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:28,fontWeight:900,color:mode==="quarterly"?"var(--cyan)":"var(--gold-l)",marginBottom:8}}>{pendingWinner.name}</div>
                    <div style={{fontFamily:"'Cinzel',serif",fontSize:13,color:modeColor,letterSpacing:3,marginBottom:5}}>{modePrize}</div>
                    <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:"var(--dim)"}}>{pendingWinner.id} · {pendingWinner.tickets} {t.tickets}</div>
                  </div>
                ) : (
                  <div className={spinning?"flash-anim":""} style={{textAlign:"center"}}>
                    {drumPlayer && <>
                      <div style={{fontFamily:"'Cinzel',serif",fontSize:28,fontWeight:700,color:modeColor,letterSpacing:4,marginBottom:5}}>{drumPlayer.id}</div>
                      <div style={{fontFamily:"'EB Garamond',serif",fontSize:18,color:"var(--text)",opacity:.8}}>{drumPlayer.name}</div>
                      {spinning && <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:getMeta(getWeight(drumPlayer),t).color,marginTop:4,letterSpacing:2}}>{getMeta(getWeight(drumPlayer),t).label}</div>}
                    </>}
                  </div>
                )}
              </div>
              <div style={{display:"flex",justifyContent:"center",gap:12}}>
                {showWinner && pendingWinner ? (
                  <button onClick={confirmWinner} style={{fontFamily:"'Cinzel',serif",fontSize:12,fontWeight:700,letterSpacing:4,padding:"13px 44px",background:`rgba(${mode==="quarterly"?"0,160,200":"180,140,20"},.12)`,border:`2px solid ${modeColor}`,color:modeColor,cursor:"pointer"}}>{t.confirm}</button>
                ) : (
                  <button onClick={startRaffle} disabled={spinning||!players.length}
                    style={{fontFamily:"'Cinzel',serif",fontSize:12,fontWeight:700,letterSpacing:4,padding:"14px 48px",background:spinning?"rgba(80,14,22,.4)":"linear-gradient(135deg,#580f18,var(--red),#580f18)",border:`2px solid ${spinning?"rgba(180,30,50,.3)":"var(--red-l)"}`,color:"white",cursor:spinning||!players.length?"not-allowed":"pointer",opacity:!players.length?.3:1}}>
                    {spinning?t.spinning:t.spin}
                  </button>
                )}
              </div>
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:6}}>
              <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)",marginBottom:3}}>{players.length} {t.participants}</div>
              <div style={{display:"flex",flexDirection:"column",gap:5,overflowY:"auto",maxHeight:"calc(100vh - 300px)"}}>
                {[...players].sort((a,b)=>getWeight(b)-getWeight(a)).map(p => (
                  <PlayerRow key={p.id} player={p} mode={mode} weeklyExcluded={weeklyExcluded}
                    quarterlyExcluded={quarterlyExcluded} t={t}
                    isWinner={showWinner&&pendingWinner?.id===p.id}
                    isDrum={spinning&&drumPlayer?.id===p.id}/>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ── FINAL NIGHT ───────────────────────────────────────────── */}
        {view==="final" && (
          <div style={{display:"grid",gridTemplateColumns:"1fr 270px",gap:18}}>
            <div style={{display:"flex",flexDirection:"column",gap:14}}>
              <div style={{textAlign:"center",padding:"10px 0"}}>
                <div style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:6,color:"rgba(232,51,74,.55)",marginBottom:6}}>{t.finalSub}</div>
                <div className="shimmer" style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:22,fontWeight:900,letterSpacing:6,
                  background:"linear-gradient(90deg,#8b1a2e,var(--red-l),#f5e17a,var(--red-l),#8b1a2e)",backgroundSize:"200% auto",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",animation:"shimmer 3s linear infinite"}}>
                  {t.finalNight}
                </div>
              </div>
              <FinalPrizeReveal revealed={grandPrizeRevealed} selected={grandPrizeType}
                onReveal={key => { setGrandPrizeType(key); setGrandPrizeRevealed(true); }}
                lang={lang} t={t} cfg={cfg} fmt={fmt}/>
              {grandPrizeRevealed && (
                <div style={{display:"flex",flexDirection:"column",gap:12}}>
                  <div style={{height:190,background:"var(--bg2)",border:`2px solid ${showWinner?"var(--red-l)":"rgba(196,30,58,.25)"}`,display:"flex",alignItems:"center",justifyContent:"center",position:"relative",animation:"bg-breathe 4s ease-in-out infinite",transition:"border-color .4s"}}>
                    {players.length===0 ? (
                      <div style={{fontFamily:"'Cinzel',serif",fontSize:11,color:"var(--dim)"}}>{t.noPart}</div>
                    ) : showWinner && pendingWinner ? (
                      <div className="winner-pop" style={{textAlign:"center",padding:20}}>
                        <div style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:5,color:"var(--red-l)",marginBottom:12}}>{t.grandWinner}</div>
                        <div className="glow-red" style={{fontFamily:"'Cinzel Decorative','Cinzel',serif",fontSize:30,fontWeight:900,color:"var(--red-l)",padding:"12px 28px",border:"2px solid var(--red-l)",marginBottom:10}}>{pendingWinner.name}</div>
                        <div style={{fontFamily:"'Cinzel',serif",fontSize:13,color:"var(--red-l)",letterSpacing:3}}>{modePrize}</div>
                      </div>
                    ) : (
                      <div className={spinning?"flash-anim":""} style={{textAlign:"center"}}>
                        {drumPlayer && <>
                          <div style={{fontFamily:"'Cinzel',serif",fontSize:28,fontWeight:700,color:"var(--red-l)",letterSpacing:4,marginBottom:5}}>{drumPlayer.id}</div>
                          <div style={{fontFamily:"'EB Garamond',serif",fontSize:18,color:"var(--text)",opacity:.8}}>{drumPlayer.name}</div>
                        </>}
                      </div>
                    )}
                  </div>
                  <div style={{display:"flex",justifyContent:"center"}}>
                    {showWinner && pendingWinner ? (
                      <button onClick={confirmWinner} className="glow-red" style={{fontFamily:"'Cinzel',serif",fontSize:13,fontWeight:700,letterSpacing:4,padding:"14px 48px",background:"rgba(196,30,58,.14)",border:"2px solid var(--red-l)",color:"var(--red-l)",cursor:"pointer"}}>{t.confirm}</button>
                    ) : (
                      <button onClick={() => { setMode("final"); startRaffle(); }} disabled={spinning||!players.length}
                        style={{fontFamily:"'Cinzel',serif",fontSize:13,fontWeight:700,letterSpacing:4,padding:"15px 52px",background:"linear-gradient(135deg,#580f18,var(--red),#580f18)",border:"2px solid var(--red-l)",color:"white",cursor:spinning||!players.length?"not-allowed":"pointer"}}>
                        {spinning?t.spinning:t.grandWinner+" →"}
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:8}}>
              <Countdown t={t}/>
              <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)",marginTop:6}}>
                {players.filter(p=>!quarterlyExcluded.includes(p.id)).length} {t.eligible} / {players.length} {t.participants}
              </div>
              <div style={{display:"flex",flexDirection:"column",gap:5,overflowY:"auto",maxHeight:"calc(100vh - 360px)"}}>
                {[...players].sort((a,b)=>b.tickets-a.tickets).map(p => (
                  <PlayerRow key={p.id} player={p} mode="final" weeklyExcluded={weeklyExcluded}
                    quarterlyExcluded={quarterlyExcluded} t={t}
                    isWinner={showWinner&&pendingWinner?.id===p.id}
                    isDrum={spinning&&drumPlayer?.id===p.id}/>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>

      <HuntTicker players={players} weeklyExcluded={weeklyExcluded} quarterlyExcluded={quarterlyExcluded} t={t}/>

      {/* OPERATOR PANEL */}
      {showPanel && (
        <div style={{position:"fixed",top:0,right:0,width:330,height:"100vh",background:"var(--bg2)",borderLeft:"1px solid rgba(212,175,55,.1)",zIndex:50,overflowY:"auto",animation:"slide-in .3s ease",padding:"18px 16px",display:"flex",flexDirection:"column",gap:13}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
            <div style={{fontFamily:"'Cinzel',serif",fontSize:10,letterSpacing:4,color:"var(--gold)"}}>{t.operator}</div>
            <button onClick={() => setShowPanel(false)} style={{background:"transparent",border:"none",color:"var(--dim)",cursor:"pointer",fontSize:18}}>✕</button>
          </div>
          <hr style={{border:"none",borderTop:"1px solid rgba(212,175,55,.08)"}}/>

          <button onClick={loadPlayers} disabled={loading} style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:3,padding:"10px",background:"rgba(212,175,55,.08)",border:"1px solid rgba(212,175,55,.22)",color:"var(--gold)",cursor:"pointer"}}>{loading?t.loading:t.loadApi}</button>
          <hr style={{border:"none",borderTop:"1px solid rgba(212,175,55,.08)"}}/>

          {/* CURRENCY */}
          <div>
            <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)",marginBottom:8}}>{t.currency}</div>
            <div style={{display:"flex",gap:5,flexWrap:"wrap"}}>
              {CURRENCIES.map(c => (
                <button key={c.code} onClick={() => setCurrency(c)}
                  style={{fontFamily:"'Cinzel',serif",fontSize:13,padding:"7px 11px",cursor:"pointer",
                    background:currency.code===c.code?"rgba(212,175,55,.15)":"transparent",
                    border:`1px solid ${currency.code===c.code?"var(--gold)":"rgba(212,175,55,.15)"}`,
                    color:currency.code===c.code?"var(--gold)":"var(--dim)"}}>
                  {c.symbol} <span style={{fontSize:8,letterSpacing:1,verticalAlign:"middle"}}>{c.code}</span>
                </button>
              ))}
            </div>
          </div>
          <hr style={{border:"none",borderTop:"1px solid rgba(212,175,55,.08)"}}/>

          {/* PRIZE AMOUNTS */}
          <div>
            <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)",marginBottom:9}}>{t.prizes}</div>
            {lbl(t.wkBase,"rgba(212,175,55,.5)")}
            {inp(cfg.weeklyBase, e => setCfg(p=>({...p,weeklyBase:+e.target.value})))}
            {lbl(t.wkGrowth,"rgba(212,175,55,.5)")}
            {inp(cfg.weeklyGrowth, e => setCfg(p=>({...p,weeklyGrowth:+e.target.value})))}
            {["Q1","Q2","Q3"].map((q,i) => (
              <div key={i}>
                {lbl(`${q} Çeyrek Ödülü`,"rgba(0,200,255,.5)")}
                <input type="number" value={cfg.quarterly[i]} onChange={e=>{const qa=[...cfg.quarterly];qa[i]=+e.target.value;setCfg(p=>({...p,quarterly:qa}));}}
                  style={{width:"100%",background:"var(--bg3)",border:"1px solid rgba(0,200,255,.15)",color:"var(--text)",padding:"6px 8px",fontFamily:"'Cinzel',serif",fontSize:11,outline:"none",marginBottom:7}}/>
              </div>
            ))}
            {lbl(t.finalCashLabel,"rgba(232,51,74,.5)")}
            {inp(cfg.finalCash, e => setCfg(p=>({...p,finalCash:+e.target.value})),"rgba(232,51,74,.2)")}
          </div>
          <hr style={{border:"none",borderTop:"1px solid rgba(212,175,55,.08)"}}/>

          {/* CAMPAIGN STATE */}
          <div>
            <div style={{fontFamily:"'Cinzel',serif",fontSize:8,letterSpacing:3,color:"var(--dim)",marginBottom:8}}>{t.campaignState}</div>
            <div style={{display:"flex",gap:8,marginBottom:8}}>
              <div style={{flex:1}}>
                {lbl(t.currentWeek)}
                <input type="number" value={weekNum} onChange={e=>{const w=+e.target.value;setWeekNum(w);setWeeklyPool(cfg.weeklyBase+w*cfg.weeklyGrowth);}}
                  style={{width:"100%",background:"var(--bg3)",border:"1px solid rgba(212,175,55,.15)",color:"var(--text)",padding:"6px 8px",fontFamily:"'Cinzel',serif",fontSize:11,outline:"none"}}/>
              </div>
              <div style={{flex:1}}>
                {lbl(t.currentQ)}
                <select value={quarterIdx} onChange={e=>setQuarterIdx(+e.target.value)}
                  style={{width:"100%",background:"var(--bg3)",border:"1px solid rgba(212,175,55,.15)",color:"var(--text)",padding:"6px 8px",fontFamily:"'Cinzel',serif",fontSize:11,outline:"none"}}>
                  {[0,1,2,3].map(i=><option key={i} value={i}>Q{i+1}</option>)}
                </select>
              </div>
            </div>
            {lbl(t.currentPool)}
            {inp(weeklyPool, e=>setWeeklyPool(+e.target.value))}
            <div style={{fontFamily:"'Cinzel',serif",fontSize:8,color:"rgba(212,175,55,.35)",marginBottom:4}}>{t.excluded}: Hf {weeklyExcluded.length} · Çyr {quarterlyExcluded.length}</div>
          </div>
          <hr style={{border:"none",borderTop:"1px solid rgba(212,175,55,.08)"}}/>

          <button onClick={() => { setWeeklyExcluded([]); setQuarterlyExcluded([]); setQuarterlyWinners([null,null,null]); setGrandPrizeType(null); setGrandPrizeRevealed(false); setShowWinner(false); setPendingWinner(null); setSpinning(false); }}
            style={{fontFamily:"'Cinzel',serif",fontSize:9,letterSpacing:3,padding:"10px",background:"transparent",border:"1px solid rgba(65,50,36,.25)",color:"rgba(100,80,55,.32)",cursor:"pointer",marginTop:"auto"}}>
            {t.reset}
          </button>
        </div>
      )}
    </div>
  );
}
