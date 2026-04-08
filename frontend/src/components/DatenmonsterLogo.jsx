export default function DatenmonsterLogo({ size = 96, className = "" }) {
  return (
    <svg
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 140 100"
      width={size}
      height={(size * 100) / 140}
      aria-hidden="true"
      style={{ display: "block", overflow: "visible" }}
    >
      <style>{`
        .dm-bg { fill: #111111; }
        .dm-panel { fill: #1a1a1a; stroke: #fce499; stroke-width: 1.5; }
        .dm-gold { fill: #fce499; }
        .dm-cyan { fill: #00ffff; }
        .dm-magenta { fill: #ff00ff; }

        .dm-monster {
          transform-origin: 50px 47px;
          animation: dm-idleBob 2s ease-in-out infinite;
        }

        @keyframes dm-idleBob {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-1px); }
        }

        .dm-head {
          transform-origin: 50px 47px;
          animation: dm-headTurn 3s infinite ease-in-out;
        }

        @keyframes dm-headTurn {
          0%, 55%, 100% { transform: rotate(0deg); }
          65%, 82% { transform: rotate(8deg); }
        }

        .dm-mouth {
          transform-origin: 50px 55px;
          animation: dm-chew 0.6s infinite;
        }

        @keyframes dm-chew {
          0%, 100% { transform: scaleY(1); }
          50% { transform: scaleY(0.82); }
        }

        .dm-inDot1 { animation: dm-moveIn 3s linear infinite; }
        .dm-inDot2 { animation: dm-moveIn 3s linear infinite 0.6s; }
        .dm-inDot3 { animation: dm-moveIn 3s linear infinite 1.2s; }

        @keyframes dm-moveIn {
          0%   { transform: translateX(0); opacity: 0; }
          8%   { opacity: 1; }
          42%  { transform: translateX(42px); opacity: 1; }
          48%  { transform: translateX(48px); opacity: 0; }
          100% { transform: translateX(48px); opacity: 0; }
        }

        .dm-outDot1 { animation: dm-moveOut 3s linear infinite; }
        .dm-outDot2 { animation: dm-moveOut 3s linear infinite 0.25s; }
        .dm-outDot3 { animation: dm-moveOut 3s linear infinite 0.5s; }

        @keyframes dm-moveOut {
          0%, 63% { transform: translateX(0); opacity: 0; }
          66%     { opacity: 1; }
          100%    { transform: translateX(40px); opacity: 0; }
        }

        .dm-convertFlash {
          animation: dm-flash 3s infinite;
          transform-origin: 50px 55px;
        }

        @keyframes dm-flash {
          0%, 56%, 100% { opacity: 0; }
          60% { opacity: 0.55; }
          68% { opacity: 0; }
        }
      `}</style>

      <rect className="dm-bg" width="140" height="100" rx="16" />

      <g>
        <circle className="dm-gold dm-inDot1" cx="2" cy="54" r="2.2" />
        <circle className="dm-gold dm-inDot2" cx="2" cy="54" r="2.2" />
        <circle className="dm-gold dm-inDot3" cx="2" cy="54" r="2.2" />
      </g>

      <g className="dm-monster">
        <rect
          x="20"
          y="22"
          width="64"
          height="56"
          rx="8"
          fill="#ff00ff"
          opacity="0.08"
        />
        <rect
          x="24"
          y="18"
          width="64"
          height="56"
          rx="8"
          fill="#00ffff"
          opacity="0.08"
        />

        <g className="dm-head">
          <rect
            x="22"
            y="20"
            width="60"
            height="54"
            rx="6"
            className="dm-panel"
          />

          <rect x="30" y="32" width="8" height="8" className="dm-gold" />
          <rect x="32" y="34" width="4" height="4" fill="#111111" />
          <rect x="66" y="32" width="8" height="8" className="dm-gold" />
          <rect x="68" y="34" width="4" height="4" fill="#111111" />

          <g className="dm-mouth">
            <rect
              x="30"
              y="48"
              width="40"
              height="14"
              rx="2"
              fill="#111111"
              stroke="#fce499"
              strokeWidth="1"
            />
            <rect x="32" y="48" width="5" height="5" className="dm-gold" />
            <rect x="40" y="48" width="5" height="5" className="dm-gold" />
            <rect x="48" y="48" width="5" height="5" className="dm-gold" />
            <rect x="56" y="48" width="5" height="5" className="dm-gold" />
            <rect x="64" y="48" width="5" height="5" className="dm-gold" />

            <rect
              x="33"
              y="55"
              width="2"
              height="4"
              className="dm-gold"
              opacity="0.7"
            />
            <rect
              x="37"
              y="56"
              width="2"
              height="3"
              className="dm-gold"
              opacity="0.5"
            />
            <rect
              x="41"
              y="54"
              width="2"
              height="5"
              className="dm-cyan"
              opacity="0.7"
            />
            <rect
              x="45"
              y="56"
              width="2"
              height="3"
              className="dm-gold"
              opacity="0.7"
            />
            <rect
              x="49"
              y="55"
              width="2"
              height="4"
              className="dm-magenta"
              opacity="0.6"
            />
            <rect
              x="53"
              y="56"
              width="2"
              height="3"
              className="dm-gold"
              opacity="0.6"
            />
            <rect
              x="57"
              y="54"
              width="2"
              height="5"
              className="dm-cyan"
              opacity="0.5"
            />
            <rect
              x="61"
              y="56"
              width="2"
              height="3"
              className="dm-gold"
              opacity="0.7"
            />
          </g>

          <rect x="32" y="12" width="4" height="10" className="dm-gold" />
          <rect x="30" y="10" width="8" height="4" className="dm-gold" />
          <rect x="68" y="12" width="4" height="10" className="dm-gold" />
          <rect x="66" y="10" width="8" height="4" className="dm-gold" />

          <circle
            className="dm-convertFlash"
            cx="50"
            cy="55"
            r="10"
            fill="#00ffff"
          />
        </g>
      </g>

      <g>
        <circle className="dm-cyan dm-outDot1" cx="73" cy="55" r="2.2" />
        <circle className="dm-magenta dm-outDot2" cx="73" cy="55" r="2.2" />
        <circle className="dm-cyan dm-outDot3" cx="73" cy="55" r="2.2" />
      </g>
    </svg>
  );
}
