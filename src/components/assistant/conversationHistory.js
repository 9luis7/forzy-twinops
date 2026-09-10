import { MAX_HISTORY_ANSWER_CHARACTERS } from "../../contracts/rag.js";

const MANUAL_HISTORY_LABEL = "Segundo o manual:\n";
const truncate = (value, budget) => value.length <= budget ? value : `${value.slice(0, budget - 1)}…`;

/** Bound conversational memory without discarding either part of the answer. */
export const completedAnswer = (response, stateLabel = "Estado atual") => {
  const currentLabel = `\n${stateLabel}:\n`;
  const available = MAX_HISTORY_ANSWER_CHARACTERS - MANUAL_HISTORY_LABEL.length - currentLabel.length;
  let manualBudget = Math.min(response.answer.manual.length, Math.floor(available / 2));
  let currentBudget = Math.min(response.answer.currentState.length, available - manualBudget);
  const manualExtra = Math.min(response.answer.manual.length - manualBudget, available - manualBudget - currentBudget);
  manualBudget += manualExtra;
  currentBudget += Math.min(response.answer.currentState.length - currentBudget, available - manualBudget - currentBudget);
  return MANUAL_HISTORY_LABEL + truncate(response.answer.manual, manualBudget)
    + currentLabel + truncate(response.answer.currentState, currentBudget);
};
