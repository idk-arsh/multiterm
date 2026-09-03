/**
 * Inline SVG icons. One 24x24 grid, 1.7 stroke, currentColor, so they sit
 * consistently next to text at any size and inherit the surrounding colour.
 */
const base = {
  width: 24,
  height: 24,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: false,
};

export const IconWorkspace = (p) => (
  <svg {...base} {...p}>
    <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l1.6 2H19a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 19 18H4.5A1.5 1.5 0 0 1 3 16.5z" />
    <path d="M8 18v2.5M16 18v2.5M12 18v2.5" opacity=".55" />
  </svg>
);

export const IconBroadcast = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="2" fill="currentColor" stroke="none" />
    <path d="M8.2 8.2a5.4 5.4 0 0 0 0 7.6M15.8 8.2a5.4 5.4 0 0 1 0 7.6" />
    <path d="M5.5 5.5a9.2 9.2 0 0 0 0 13M18.5 5.5a9.2 9.2 0 0 1 0 13" opacity=".55" />
  </svg>
);

export const IconSplit = (p) => (
  <svg {...base} {...p}>
    <rect x="3" y="4.5" width="18" height="15" rx="2.2" />
    <path d="M12 4.5v15" />
    <path d="M16.5 9.5v5" opacity=".55" />
  </svg>
);

export const IconSearch = (p) => (
  <svg {...base} {...p}>
    <circle cx="11" cy="11" r="6" />
    <path d="M15.6 15.6 20 20" />
  </svg>
);

export const IconShells = (p) => (
  <svg {...base} {...p}>
    <rect x="3" y="4.5" width="18" height="15" rx="2.2" />
    <path d="M7 9.5l2.6 2.5L7 14.5" />
    <path d="M12.5 15h4.5" />
  </svg>
);

export const IconSpeed = (p) => (
  <svg {...base} {...p}>
    <path d="M12 20a8 8 0 1 1 8-8" />
    <path d="M12 12l4.2-3.2" />
    <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
  </svg>
);

export const IconCheck = (p) => (
  <svg {...base} strokeWidth="2.2" {...p}>
    <path d="M4.5 12.5 9.5 17.5 19.5 6.5" />
  </svg>
);

export const IconDot = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none" opacity=".6" />
  </svg>
);

export const IconDownload = (p) => (
  <svg {...base} {...p}>
    <path d="M12 4v10" />
    <path d="M8 10.5 12 14.5 16 10.5" />
    <path d="M5 17.5v1A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5v-1" />
  </svg>
);

export const IconKey = (p) => (
  <svg {...base} {...p}>
    <circle cx="8" cy="12" r="3.5" />
    <path d="M11.5 12H20" />
    <path d="M17 12v3M14 12v2.2" />
  </svg>
);

export const IconCard = (p) => (
  <svg {...base} {...p}>
    <rect x="3" y="6" width="18" height="12" rx="2.2" />
    <path d="M3 10h18" />
    <path d="M7 14.5h3" opacity=".6" />
  </svg>
);

export const IconWindows = (p) => (
  <svg {...base} strokeWidth="1.5" {...p}>
    <path d="M4 7.2 11 6v5.4H4z" />
    <path d="M12.4 5.8 20 4.6v6.8h-7.6z" />
    <path d="M4 12.6h7V18l-7-1.2z" />
    <path d="M12.4 12.6H20v6.8l-7.6-1.2z" />
  </svg>
);

export const IconArrow = (p) => (
  <svg {...base} {...p}>
    <path d="M5 12h13" />
    <path d="M13 6.5 18.5 12 13 17.5" />
  </svg>
);
