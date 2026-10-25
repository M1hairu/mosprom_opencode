// Line icons 24 × 24 for the tab bar. Colour comes from the text (currentColor).
import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {children}
    </svg>
  );
}

export const IconRoute = () => (
  <Icon>
    <circle cx="6" cy="18" r="2.5" />
    <circle cx="18" cy="6" r="2.5" />
    <path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5" />
  </Icon>
);

export const IconMap = () => (
  <Icon>
    <path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20Z" />
    <path d="M9 4v13.5M15 6.5V20" />
  </Icon>
);

export const IconAsk = () => (
  <Icon>
    <path d="M4 5h16v11H9l-5 4Z" />
    <path d="M10 9a2 2 0 1 1 2.5 1.9c-.3.1-.5.4-.5.7V12M12 14.2v.1" />
  </Icon>
);

export const IconRequest = () => (
  <Icon>
    <path d="M6 3h9l4 4v14H6Z" />
    <path d="M9 12h7M9 16h5M14 3v5h5" />
  </Icon>
);
