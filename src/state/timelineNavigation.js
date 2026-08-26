const EMPTY_LOADING = Object.freeze({
  overview: false,
  page: false,
  assessments: false,
  context: false,
});

const EMPTY_ERRORS = Object.freeze({
  overview: null,
  page: null,
  assessments: null,
  context: null,
});

export const initialTimelineNavigationState = Object.freeze({
  viewMode: "now",
  timelineOverview: null,
  timelinePage: null,
  timelineAssessmentOverview: null,
  pendingSelection: null,
  historicalContext: null,
  loading: EMPTY_LOADING,
  errors: EMPTY_ERRORS,
});

const withRequestState = (state, key, loading, error) => ({
  ...state,
  loading: { ...state.loading, [key]: loading },
  errors: { ...state.errors, [key]: error },
});

const copySelection = (selection) => {
  if (selection === null || typeof selection !== "object" || Array.isArray(selection)) {
    throw new TypeError("CONTEXT_REQUESTED selection must be an object");
  }
  const keys = Object.keys(selection);
  if (keys.length === 1 && keys[0] === "pointId") {
    return Object.freeze({ pointId: selection.pointId });
  }
  if (keys.length === 2 && keys.includes("at") && keys.includes("segmentId")) {
    return Object.freeze({ at: selection.at, segmentId: selection.segmentId });
  }
  throw new TypeError("CONTEXT_REQUESTED selection must be pointId or at with segmentId");
};

export function timelineNavigationReducer(state, action) {
  switch (action?.type) {
    case "RESET":
      return initialTimelineNavigationState;
    case "SHOW_HISTORY":
      return state.viewMode === "historical" ? state : { ...state, viewMode: "historical" };
    case "SHOW_NOW":
      return {
        ...state,
        viewMode: "now",
        pendingSelection: null,
        loading: EMPTY_LOADING,
        errors: { ...state.errors, context: null },
      };
    case "OVERVIEW_REQUESTED":
      return withRequestState(state, "overview", true, null);
    case "OVERVIEW_RESOLVED":
      return {
        ...withRequestState(state, "overview", false, null),
        timelineOverview: action.overview,
      };
    case "OVERVIEW_FAILED":
      return withRequestState(state, "overview", false, action.error);
    case "PAGE_REQUESTED":
      return withRequestState(state, "page", true, null);
    case "PAGE_RESOLVED":
      return {
        ...withRequestState(state, "page", false, null),
        timelinePage: action.page,
      };
    case "PAGE_FAILED":
      return withRequestState(state, "page", false, action.error);
    case "ASSESSMENTS_REQUESTED":
      return withRequestState(state, "assessments", true, null);
    case "ASSESSMENTS_RESOLVED":
      if (action.assessmentOverview === null
        || typeof action.assessmentOverview !== "object"
        || Array.isArray(action.assessmentOverview)) {
        throw new TypeError("ASSESSMENTS_RESOLVED assessmentOverview must be an object");
      }
      return {
        ...withRequestState(state, "assessments", false, null),
        timelineAssessmentOverview: action.assessmentOverview,
      };
    case "ASSESSMENTS_FAILED":
      return withRequestState(state, "assessments", false, action.error);
    case "BUNDLE_RESOLVED": {
      const bundle = action.bundle;
      const keys = bundle !== null && typeof bundle === "object" && !Array.isArray(bundle)
        ? Object.keys(bundle).sort()
        : [];
      if (
        keys.join(",") !== "assessmentOverview,overview,page"
        || [bundle?.overview, bundle?.page, bundle?.assessmentOverview].some(
          (value) => value === null || typeof value !== "object" || Array.isArray(value),
        )
      ) throw new TypeError("BUNDLE_RESOLVED bundle must contain overview, page, and assessmentOverview objects");
      return {
        ...state,
        timelineOverview: bundle.overview,
        timelinePage: bundle.page,
        timelineAssessmentOverview: bundle.assessmentOverview,
        loading: {
          ...state.loading,
          overview: false,
          page: false,
          assessments: false,
        },
        errors: {
          ...state.errors,
          overview: null,
          page: null,
          assessments: null,
        },
      };
    }
    case "CONTEXT_REQUESTED":
      return {
        ...withRequestState(state, "context", true, null),
        pendingSelection: copySelection(action.selection),
      };
    case "CONTEXT_RESOLVED":
      if (action.context === null || typeof action.context !== "object" || Array.isArray(action.context)) {
        throw new TypeError("CONTEXT_RESOLVED context must be an object");
      }
      return {
        ...withRequestState(state, "context", false, null),
        viewMode: "historical",
        pendingSelection: null,
        historicalContext: action.context,
      };
    case "CONTEXT_FAILED":
      return {
        ...withRequestState(state, "context", false, action.error),
        pendingSelection: null,
      };
    default:
      throw new TypeError(`Unknown timeline navigation action: ${action?.type ?? "undefined"}`);
  }
}

export function committedTimelineContext(state, nowSnapshot) {
  return state.viewMode === "historical" && state.historicalContext !== null
    ? state.historicalContext
    : nowSnapshot;
}
