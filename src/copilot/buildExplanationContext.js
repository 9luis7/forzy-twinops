export function buildExplanationRequest({ question, snapshot }) {
  const normalizedQuestion = String(question ?? "").trim();
  if (!normalizedQuestion) throw new TypeError("question is required");
  if (!snapshot?.assetTag) throw new TypeError("snapshot.assetTag is required");
  if (!snapshot.assessment) throw new TypeError("snapshot.assessment is required");

  return {
    question: normalizedQuestion,
    assetTag: snapshot.assetTag,
    assessment: snapshot.assessment,
  };
}
