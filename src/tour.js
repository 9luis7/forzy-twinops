// tour.js — roteiro do MODO APRESENTAÇÃO (tour guiado).
//
// Conta a história do demo em pt-BR, do gêmeo digital da planta até a auditoria do dado.
// Cada passo descreve: para qual view ir (view), qual motor abrir (asset, ou null),
// qual elemento destacar (target = valor de data-tour, ou null) e o texto do apresentador.
// Consumido por GuidedTour.jsx (TourProvider/TourOverlay).

export const TOUR_STEPS = [
  {
    id: "plant",
    view: "planta",
    asset: null,
    target: "plant-synoptic",
    title: "A planta como gêmeo digital",
    text: "128 ativos monitorados ao vivo. Áreas e motores acendem conforme o estado real — 3 pedem atenção agora.",
  },
  {
    id: "drill",
    view: "ativos",
    asset: "MTR-BMB-042",
    target: "motor-mimic",
    title: "O motor sob suspeita",
    text: "O gêmeo nos leva ao MTR-BMB-042. Cada sensor está desenhado no seu ponto físico real.",
  },
  {
    id: "bearing",
    view: "ativos",
    asset: "MTR-BMB-042",
    target: "motor-mimic",
    title: "Onde o risco mora",
    text: "O rolamento do lado acoplamento está aceso: é o componente que está degradando.",
  },
  {
    id: "telemetry",
    view: "ativos",
    asset: "MTR-BMB-042",
    target: "telemetry",
    title: "Telemetria ao vivo",
    text: "Temperatura e vibração subindo em tempo real. Você pode iniciar a simulação ou disparar um incidente.",
  },
  {
    id: "audit",
    view: "auditoria",
    asset: "MTR-BMB-042",
    target: "audit",
    title: "Por que confiar no dado",
    text: "De onde veio, se não foi adulterado e quem validou. A recomendação é auditável de ponta a ponta.",
  },
];

export default TOUR_STEPS;
