// Suggestions use already displayed context. Building them never calls an LLM.
export function promptSuggestions({ status = "unknown", sensor = "s1", answered = false } = {}) {
  const attention = status === "watch" || status === "alert";
  const readings = sensor === "s2"
    ? { label: "Entender os dados da bomba", question: "Quais leituras e limitações dos dados de S2 estão disponíveis neste instante? Não solicito procedimentos de manutenção da bomba." }
    : { label: attention ? "Por que o motor pede atenção?" : "Entender os dados do motor", question: attention ? "Quais evidências justificam a atenção do motor S1 neste instante?" : "Quais evidências e limitações dos dados do motor S1 estão disponíveis neste instante?" };
  return [
    readings,
    { label: answered ? "Verificar lubrificação" : "O que verificar no motor?", question: answered ? "Que verificações de lubrificação o manual WEG W22 orienta para o motor?" : "Que verificações de vibração e rolamentos o manual WEG W22 orienta para o motor?" },
    { label: "Cuidados do manual", question: "Quais cuidados de segurança o manual WEG W22 orienta antes da inspeção do motor?" },
  ];
}
