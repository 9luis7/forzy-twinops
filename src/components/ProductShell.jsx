import React from "react";
import "../product.css";

export default function ProductShell({ pathname, children }) {
  const section = pathname.replace(/\/$/, "") || "/";
  return (
    <div className="product-shell">
      <a className="skip-navigation" href="#workspace">Ir para o conteúdo</a>
      <header className="product-navigation">
        <a className="product-brand" href="/" aria-label="TwinOps — visão geral">
          <img className="product-brand__symbol" src="/brand/twinops-symbol.png" width="48" height="48" alt="" />
          <strong>TwinOps</strong><span className="product-brand__endorsement">by FORZY</span>
        </a>
        <nav aria-label="Navegação principal">
          <a href="/" aria-current={section === "/" ? "page" : undefined}>Visão geral</a>
          <a href="/history" aria-current={section === "/history" ? "page" : undefined}>Histórico</a>
        </nav>
        <a className="product-demo-link" href="/demo" aria-current={section === "/demo" ? "page" : undefined}>Demonstração</a>
      </header>
      <div id="workspace" tabIndex={-1}>{children}</div>
    </div>
  );
}
