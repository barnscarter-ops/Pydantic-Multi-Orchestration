/* Custom illustrated character for each agent — small SVG faces with personality */

export function PlannerChar({ active }) {
  return (
    <svg viewBox="0 0 40 46" fill="none" xmlns="http://www.w3.org/2000/svg" className={`agent-char ${active ? "char-active" : ""}`}>
      {/* Pointy wizard hat */}
      <polygon points="20,1 11,17 29,17" fill="#1a3060" stroke="#60a0ff" strokeWidth="1.2"/>
      <line x1="11" y1="17" x2="29" y2="17" stroke="#60a0ff" strokeWidth="1.5"/>
      {/* Hat star */}
      <polygon points="20,4 20.8,6.4 23.4,6.4 21.3,7.8 22.1,10.2 20,8.8 17.9,10.2 18.7,7.8 16.6,6.4 19.2,6.4" fill="#60a0ff" opacity="0.9"/>
      {/* Face */}
      <circle cx="20" cy="30" r="13" fill="#111e38" stroke="#60a0ff" strokeWidth="1.5"/>
      {/* Glasses frames */}
      <circle cx="14.5" cy="29" r="4" fill="none" stroke="#60a0ff" strokeWidth="1.3"/>
      <circle cx="25.5" cy="29" r="4" fill="none" stroke="#60a0ff" strokeWidth="1.3"/>
      <line x1="18.5" y1="29" x2="21.5" y2="29" stroke="#60a0ff" strokeWidth="1.2"/>
      {/* Nose bridge over glasses */}
      <line x1="10.5" y1="29" x2="10" y2="29" stroke="#60a0ff" strokeWidth="1"/>
      <line x1="29.5" y1="29" x2="30" y2="29" stroke="#60a0ff" strokeWidth="1"/>
      {/* Pupils */}
      <circle cx="14.5" cy="29" r="1.8" fill="#60a0ff" opacity="0.85"/>
      <circle cx="25.5" cy="29" r="1.8" fill="#60a0ff" opacity="0.85"/>
      {/* Glint */}
      <circle cx="15.4" cy="28.2" r="0.7" fill="white" opacity="0.7"/>
      <circle cx="26.4" cy="28.2" r="0.7" fill="white" opacity="0.7"/>
      {/* Thoughtful smile */}
      <path d="M15,35 Q20,38 25,35" stroke="#60a0ff" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
      {/* Bushy eyebrows */}
      <path d="M11,24 Q14.5,22.5 18,24" stroke="#60a0ff" strokeWidth="1.4" fill="none" strokeLinecap="round"/>
      <path d="M23,24 Q26.5,22.5 30,24" stroke="#60a0ff" strokeWidth="1.4" fill="none" strokeLinecap="round"/>
    </svg>
  );
}

export function ReviewerChar({ active }) {
  return (
    <svg viewBox="0 0 40 46" fill="none" xmlns="http://www.w3.org/2000/svg" className={`agent-char ${active ? "char-active" : ""}`}>
      {/* Detective hat brim */}
      <rect x="6" y="15" width="28" height="3" rx="1.5" fill="#7a3800" stroke="#ffa060" strokeWidth="1"/>
      {/* Hat top */}
      <rect x="11" y="5" width="18" height="12" rx="2" fill="#7a3800" stroke="#ffa060" strokeWidth="1"/>
      {/* Hat band */}
      <rect x="11" y="13" width="18" height="2.5" rx="0" fill="#ffa060" opacity="0.5"/>
      {/* Face */}
      <circle cx="20" cy="32" r="12" fill="#1e1008" stroke="#ffa060" strokeWidth="1.5"/>
      {/* Left normal eye */}
      <ellipse cx="15" cy="31" rx="3" ry="2.5" fill="#ffa060" opacity="0.75"/>
      <circle cx="15.8" cy="30.4" r="0.9" fill="white" opacity="0.7"/>
      {/* Monocle ring */}
      <circle cx="25" cy="31" r="4.5" fill="none" stroke="#ffa060" strokeWidth="1.6"/>
      <ellipse cx="25" cy="31" rx="2.8" ry="2.5" fill="#ffa060" opacity="0.75"/>
      <circle cx="25.8" cy="30.4" r="0.9" fill="white" opacity="0.7"/>
      {/* Monocle cord */}
      <path d="M29,33 Q31,36 30,38" stroke="#ffa060" strokeWidth="1" fill="none" strokeLinecap="round"/>
      {/* Stern flat mouth */}
      <line x1="16" y1="37" x2="24" y2="37" stroke="#ffa060" strokeWidth="1.4" strokeLinecap="round"/>
      {/* Sharp angled left brow */}
      <path d="M12,26 L18,25" stroke="#ffa060" strokeWidth="1.5" strokeLinecap="round"/>
      {/* Raised right brow over monocle */}
      <path d="M21,25 Q25,22.5 29,25" stroke="#ffa060" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
      {/* Cheekbone line */}
      <path d="M9,34 Q11,36 12,35" stroke="#ffa060" strokeWidth="0.8" fill="none" opacity="0.5"/>
    </svg>
  );
}

export function ExecutorChar({ active }) {
  return (
    <svg viewBox="0 0 40 46" fill="none" xmlns="http://www.w3.org/2000/svg" className={`agent-char ${active ? "char-active" : ""}`}>
      {/* Antenna */}
      <line x1="20" y1="2" x2="20" y2="9" stroke="#50d890" strokeWidth="1.5" strokeLinecap="round"/>
      <circle cx="20" cy="2" r="2.2" fill="#50d890" opacity={active ? 1 : 0.7}/>
      {/* Robot head - rounded square */}
      <rect x="7" y="9" width="26" height="24" rx="5" fill="#0a1e12" stroke="#50d890" strokeWidth="1.5"/>
      {/* LED left eye */}
      <rect x="11" y="15" width="7" height="5" rx="1.5" fill="#50d890" opacity="0.9"/>
      <rect x="12.5" y="16" width="2" height="3" rx="0.5" fill="white" opacity="0.5"/>
      {/* LED right eye */}
      <rect x="22" y="15" width="7" height="5" rx="1.5" fill="#50d890" opacity="0.9"/>
      <rect x="23.5" y="16" width="2" height="3" rx="0.5" fill="white" opacity="0.5"/>
      {/* Grid mouth */}
      <rect x="12" y="23" width="16" height="6" rx="1.5" fill="none" stroke="#50d890" strokeWidth="1.2"/>
      <line x1="16" y1="23" x2="16" y2="29" stroke="#50d890" strokeWidth="0.8"/>
      <line x1="20" y1="23" x2="20" y2="29" stroke="#50d890" strokeWidth="0.8"/>
      <line x1="24" y1="23" x2="24" y2="29" stroke="#50d890" strokeWidth="0.8"/>
      {/* Ear bolt circles */}
      <circle cx="6" cy="20" r="2.5" fill="#0a1e12" stroke="#50d890" strokeWidth="1.2"/>
      <circle cx="34" cy="20" r="2.5" fill="#0a1e12" stroke="#50d890" strokeWidth="1.2"/>
      {/* Circuit line detail on forehead */}
      <path d="M14,12 L20,12 L20,10" stroke="#50d890" strokeWidth="0.7" fill="none" opacity="0.5"/>
      <path d="M26,12 L20,12" stroke="#50d890" strokeWidth="0.7" fill="none" opacity="0.5"/>
    </svg>
  );
}

export function DesignerChar({ active }) {
  return (
    <svg viewBox="0 0 40 46" fill="none" xmlns="http://www.w3.org/2000/svg" className={`agent-char ${active ? "char-active" : ""}`}>
      {/* Beret base */}
      <ellipse cx="20" cy="16" rx="15" ry="7" fill="#6010a0" stroke="#d088ff" strokeWidth="1.2"/>
      {/* Beret puff to the side */}
      <ellipse cx="27" cy="13" rx="5" ry="4" fill="#8030c0" stroke="#d088ff" strokeWidth="1"/>
      {/* Pompom */}
      <circle cx="29" cy="11" r="2.5" fill="#d088ff" opacity="0.9"/>
      {/* Face */}
      <circle cx="20" cy="32" r="12" fill="#180a28" stroke="#d088ff" strokeWidth="1.5"/>
      {/* Star left eye - layered circles for sparkle */}
      <circle cx="15" cy="31" r="3" fill="#d088ff" opacity="0.85"/>
      <circle cx="15" cy="31" r="1.2" fill="white" opacity="0.9"/>
      <circle cx="15.7" cy="30.3" r="0.5" fill="white"/>
      {/* Star right eye */}
      <circle cx="25" cy="31" r="3" fill="#d088ff" opacity="0.85"/>
      <circle cx="25" cy="31" r="1.2" fill="white" opacity="0.9"/>
      <circle cx="25.7" cy="30.3" r="0.5" fill="white"/>
      {/* Curved happy eyebrows */}
      <path d="M12,26.5 Q15,24.5 18,26.5" stroke="#d088ff" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
      <path d="M22,26.5 Q25,24.5 28,26.5" stroke="#d088ff" strokeWidth="1.3" fill="none" strokeLinecap="round"/>
      {/* Big smile */}
      <path d="M15,37 Q20,41 25,37" stroke="#d088ff" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
      {/* Paint smudge accents */}
      <circle cx="28" cy="35" r="2" fill="#ffa060" opacity="0.55"/>
      <circle cx="10" cy="35" r="1.5" fill="#50d890" opacity="0.5"/>
      <circle cx="29" cy="38" r="1" fill="#60a0ff" opacity="0.45"/>
    </svg>
  );
}
