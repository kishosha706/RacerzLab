const setupControlPattern = [
  "cross[ -]?weight",
  "corner[ -]?weight",
  "ballast",
  "wedge",
  "nose[ -]?weight",
  "left[ -]?side[ -]?weight",
  "weight[ -]?jacker",
  "pressure[ -]?(?:split|gain)",
  "brake[ -]?bias",
  "ride[ -]?height",
  "shock(?:[ -]?collar)?",
  "damper",
  "spring(?:[ -]?(?:rate|perch|platform))?",
  "tire[ -]?pressure",
  "(?:front|rear)[ -]?(?:arb|anti[ -]?roll[ -]?bar|sway[ -]?bar)(?:[ -]?(?:diameter|arm|preload|attach))?",
  "(?:arb|anti[ -]?roll[ -]?bar|sway[ -]?bar)(?:[ -]?(?:diameter|arm|preload|attach))?",
  "(?:front|rear)[ -]?toe",
  "(?:lf|rf|lr|rr)[ -]?(?:camber|caster|toe(?:[ -]?in)?)",
  "camber",
  "caster",
  "track[ -]?bar",
  "truck[ -]?arm",
  "bump[ -]?(?:stop|rubber)",
  "packer",
  "diff(?:erential)?[ -]?preload",
  "(?:front|rear)[ -]?master[ -]?cylinder",
  "(?:front|rear)[ -]?mc(?:[ -]?mm)?",
  "rear[ -]?end[ -]?ratio",
  "gear(?:[ -]?ratio)?",
  "final[ -]?drive",
  "(?:front|rear)[ -]?platform",
  "diffuser[ -]?platform",
  "splitter",
  "rub[ -]?block",
  "steering[ -]?(?:ratio|offset)",
  "tape(?:[ -]?percent)?",
  "(?:lf|rf|lr|rr)[ -]?(?:(?:cold[ -]?)?pressure|spring|shock|damper|ride[ -]?height)",
  "(?:(?:lf|rf|lr|rr)[ -]?)?(?:(?:low|high)[ -]?speed|ls|hs)[ -]?(?:comp(?:ression)?|reb(?:ound)?)(?:[ -]?slope)?",
].join("|");

const setupActionPattern = [
  "set",
  "change",
  "increase",
  "decrease",
  "raise",
  "lower",
  "add",
  "reduce",
  "soften",
  "stiffen",
  "switch",
  "move",
  "adjust",
  "trim",
  "tune",
].join("|");

const setupDirectiveBeforeControl = new RegExp(
  `\\b(?:${setupActionPattern})\\b[^.!?\\n]{0,64}\\b(?:${setupControlPattern})\\b`,
  "i",
);
const setupDirectiveAfterControl = new RegExp(
  `\\b(?:${setupControlPattern})\\b[^.!?\\n]{0,64}\\b(?:${setupActionPattern})\\b`,
  "i",
);
const exactValuePattern = String.raw`[+-]?\d+(?:\.\d+)?\s*(?:%|psi|kpa|bar|lb\/?in|n\/?mm|clicks?|in(?:ches)?|mm|deg(?:rees)?|:1)?`;
const spelledNumberToken = "(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)";
const spelledValuePattern = `${spelledNumberToken}(?:[ -]+${spelledNumberToken}){0,4}`;
const setupControlBeforeExactValue = new RegExp(
  `\\b(?:${setupControlPattern})\\b[^.!?\\n]{0,64}${exactValuePattern}`,
  "i",
);
const exactValueBeforeSetupControl = new RegExp(
  `${exactValuePattern}[^.!?\\n]{0,64}\\b(?:${setupControlPattern})\\b`,
  "i",
);
const setupControlBeforeSpelledValue = new RegExp(
  `\\b(?:${setupControlPattern})\\b[^.!?\\n]{0,64}\\b${spelledValuePattern}\\b`,
  "i",
);
const spelledValueBeforeSetupControl = new RegExp(
  `\\b${spelledValuePattern}\\b[^.!?\\n]{0,64}\\b(?:${setupControlPattern})\\b`,
  "i",
);
const targetLanguageBeforeControl = new RegExp(
  `\\b(?:use|choose|select|target|setpoint|should|must|needs?\\s+to|ought\\s+to)\\b[^.!?\\n]{0,64}\\b(?:${setupControlPattern})\\b`,
  "i",
);
const targetLanguageAfterControl = new RegExp(
  `\\b(?:${setupControlPattern})\\b[^.!?\\n]{0,64}\\b(?:use|choose|select|target|setpoint|should|must|needs?\\s+to|ought\\s+to)\\b`,
  "i",
);
const exactTransition = /(?:^|\s)[+-]?\d+(?:\.\d+)?\s*(?:%|psi|kpa|lb\/?in|n\/?mm|clicks?)?\s*(?:->|→)\s*[+-]?\d+(?:\.\d+)?/i;
const directPolicy = /(?:^|[.!?]\s+)(?:(?:keep|undo)(?:\s+it)?(?=[.!?]|$)|(?:(?:keep|retain|accept|hold|lock\s+in|stay\s+with)|(?:undo|revert|reverse|restore|roll\s+back|go\s+back\s+to|return\s+to))\s+(?:(?:this|the|that|new|current|previous)\s+)*(?:change|setup|direction|test|setting|adjustment)\b|(?:(?:this|the|that|new|current|previous)\s+)*(?:change|setup|direction|test|setting|adjustment)\s+(?:is|was|should\s+be|must\s+be)\s+(?:a\s+)?(?:keep|undo|reverted|restored|rolled\s+back)\b|(?:rollback|roll\s+back|revert|undo)(?:\s+it)?(?:\s+now)?(?=[.!?]|$))/i;
const directStop = /(?:^|[.!?]\s+)(?:(?:stop|end|cease|halt|discontinue)\s+(?:further\s+)?(?:testing|the\s+test|this\s+test)|do\s+not\s+(?:continue\s+testing|test\s+again)|don't\s+(?:continue\s+testing|test\s+again)|no\s+more\s+testing|testing\s+(?:can|should|must|may)\s+(?:now\s+)?(?:stop|end|cease)|testing\s+is\s+(?:now\s+)?over|we(?:'re|\s+are)\s+done\s+testing)\b/i;

/**
 * Reject prose that tries to smuggle setup or policy authority through a
 * non-authoritative field.
 * @param {unknown} value
 * @returns {boolean}
 */
export function hasSetupAuthorityDirective(value) {
  if (typeof value !== "string") return false;
  const text = value.trim().replace(/_/g, " ").replace(/\b\.(?=\w)/g, " ");
  return setupDirectiveBeforeControl.test(text)
    || setupDirectiveAfterControl.test(text)
    || setupControlBeforeExactValue.test(text)
    || exactValueBeforeSetupControl.test(text)
    || setupControlBeforeSpelledValue.test(text)
    || spelledValueBeforeSetupControl.test(text)
    || targetLanguageBeforeControl.test(text)
    || targetLanguageAfterControl.test(text)
    || exactTransition.test(text)
    || directPolicy.test(text)
    || directStop.test(text);
}
