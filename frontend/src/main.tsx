import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "katex/dist/katex.min.css";
import "./kit/styles/fonts";
import "./kit/styles/tokens.css";
import "./styles.css";
import { StudyApp } from "./app/StudyApp";
import { Landing } from "./landing/Landing";

function Root() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const on = () => setHash(location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const inApp = hash.startsWith("#app");
  useEffect(() => {
    if (!inApp && hash === "#top") window.scrollTo({ top: 0 });
  }, [inApp, hash]);
  return inApp ? <StudyApp /> : <Landing />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
