const needsAttention = (sensor) => ["watch", "alert"].includes(sensor?.assessment?.assessment?.status);

/** Suggestions describe the current server context; generating them does not call AI. */
export function demoSuggestions(context) {
  const suggestions = [];
  if (needsAttention(context?.sensors?.s1)) suggestions.push({
    label: "Por que o motor exige atenção?",
    question: "Quais evidências deste instante justificam a atenção do motor S1? Resuma os sinais e indique o que verificar no motor segundo o manual.",
  });
  if (needsAttention(context?.sensors?.s2)) suggestions.push({
    label: "Entender a atenção da bomba",
    question: "Quais evidências deste instante justificam a atenção da bomba S2? Resuma apenas os sinais medidos, sem recomendar procedimentos da bomba com o manual do motor.",
  });
  if (!suggestions.length) suggestions.push({
    label: "Resumir este instante",
    question: "Resuma o estado do motor S1 e da bomba S2 neste instante e os principais sinais medidos.",
  });
  suggestions.push({ label: "O que verificar no motor?", question: "Quais verificações do motor WEG W22 o manual orienta para os sinais observados neste instante? Resuma os próximos passos." });
  return suggestions;
}
