// The setup questions, in everyday words, and what each answer does to the starting weights.
//
// Two lengths. "Simple" asks five things and leaves everything else at the defaults; "more"
// asks fifteen, each sharpening one factor. An answer only moves where the sliders START
// (GOAL.md Principle 7: the visitor owns the final trade-off), and only through a factor the
// data measures, so every question here has one behind it. "Small town or big city?" is
// deliberately not asked: the town-size factor scores against a fixed population band, so a
// weight could not say which way a visitor leans.
//
// An option can carry:
//   scale  multiply a factor's default weight (nature x1.35 for "mostly nature")
//   share  give a factor a fixed number of the 100 points, for factors whose default is 0
//          (schools, local jobs) or that one answer decides (flights to Europe)
//   set    settings it decides directly (one map or two, kids)

export const QUESTIONS = {
  who: {
    title: "Who's moving?",
    sub: "Moving as a couple? You'll share one map: invite your partner after setup.",
    layout: "two",
    options: [
      { value: "solo", label: "Just me", set: { mode: "single", kids: "none" } },
      { value: "couple", label: "Me and a partner", set: { mode: "couple", kids: "none" } },
      { value: "kids", label: "Me and my kids", set: { mode: "single", kids: "now" }, share: { schools: 14 } },
      { value: "family", label: "My partner, our kids and me", set: { mode: "couple", kids: "now" }, share: { schools: 14 } },
    ],
  },
  kidsFuture: {
    title: "Kids in the next few years?",
    sub: "Good schools and childcare count for more if so.",
    layout: "three",
    when: (s) => s.kids !== "now",
    options: [
      { value: "no", label: "No", set: { kids: "none" } },
      { value: "maybe", label: "Maybe someday", set: { kids: "planned" }, share: { schools: 4 } },
      { value: "yes", label: "Yes, probably", set: { kids: "planned" }, share: { schools: 9 } },
    ],
  },
  cost: {
    title: "How careful do you need to be with money?",
    layout: "rows",
    options: [
      { value: "tight", label: "Every dollar counts", sub: "Cheaper places rise to the top.", scale: { cost: 1.6 } },
      { value: "value", label: "Good value, within reason", sub: "Price matters as much as anything else." },
      { value: "loose", label: "I'll pay more for the right place", sub: "Price counts for less.", scale: { cost: 0.6 } },
    ],
  },
  weather: {
    title: "How much does the weather affect your mood?",
    layout: "three",
    options: [
      { value: "lots", label: "A lot", sub: "Grey weeks get to me.", scale: { climate: 1.5 } },
      { value: "some", label: "Some" },
      { value: "little", label: "Hardly at all", scale: { climate: 0.5 } },
    ],
  },
  nature: {
    title: "Nature or city?",
    sub: "Where would you rather spend your free time?",
    layout: "rows",
    options: [
      { value: "wild", label: "Trails and quiet", sub: "Mountains, lakes and parks over restaurants.", scale: { nature: 1.8, food: 0.55 } },
      { value: "outdoorsy", label: "Mostly nature, some city", scale: { nature: 1.35, food: 0.8 } },
      { value: "mix", label: "A bit of both" },
      { value: "urban", label: "Mostly city, some nature", scale: { nature: 0.8, food: 1.35 } },
      { value: "city", label: "Restaurants, shows and nightlife", sub: "A lively downtown over the outdoors.", scale: { nature: 0.55, food: 1.8 } },
    ],
  },
  saturday: {
    title: "A perfect Saturday looks like…",
    layout: "two",
    options: [
      { value: "outdoors", label: "Out on a trail or the water", scale: { nature: 1.25 } },
      { value: "downtown", label: "Coffee, shops and dinner downtown", scale: { food: 1.25 } },
      { value: "people", label: "A local game, a festival or friends over", scale: { community: 1.4 } },
      { value: "home", label: "A quiet day at home" },
    ],
  },
  safety: {
    title: "How much does safety weigh on you?",
    sub: "Measured by road, overdose and firearm deaths, and crime where it's reported.",
    layout: "rows",
    options: [
      { value: "top", label: "It's my top priority", scale: { safety: 1.5 } },
      { value: "normal", label: "As much as for anyone" },
      { value: "less", label: "Less than other things", scale: { safety: 0.7 } },
    ],
  },
  hazard: {
    title: "Hurricanes, floods, wildfires, tornadoes: how much do they worry you?",
    layout: "three",
    options: [
      { value: "lots", label: "A lot", sub: "Keep me clear of them.", scale: { hazard: 1.6 } },
      { value: "some", label: "Somewhat" },
      { value: "little", label: "Not much", scale: { hazard: 0.6 } },
    ],
  },
  health: {
    title: "How often do you need doctors or a good hospital nearby?",
    layout: "three",
    options: [
      { value: "often", label: "Regularly", scale: { health: 1.6 } },
      { value: "sometimes", label: "Now and then" },
      { value: "rarely", label: "Rarely", scale: { health: 0.7 } },
    ],
  },
  work: {
    title: "How do you earn a living?",
    layout: "two",
    options: [
      { value: "remote", label: "I can work from anywhere", set: { income: "portable" }, share: { jobs: 0 } },
      { value: "partly", label: "Partly tied to a place", set: { income: "partly" }, share: { jobs: 7 } },
      { value: "local", label: "I'll need to find work there", set: { income: "local" }, share: { jobs: 14 } },
      { value: "retired", label: "I'm retired", set: { income: "portable" }, share: { jobs: 0 }, scale: { health: 1.2 } },
    ],
  },
  flights: {
    title: "How often do you fly to Europe?",
    sub: "Scored by nonstop flights to Europe from the best airport within reach.",
    layout: "three",
    options: [
      { value: "often", label: "Several times a year", set: { flights: "often" }, share: { airport: 12 } },
      { value: "sometimes", label: "Every year or two", set: { flights: "sometimes" }, share: { airport: 5 } },
      { value: "rarely", label: "Rarely or never", set: { flights: "rarely" }, share: { airport: 2 } },
    ],
  },
  neighbors: {
    title: "How well do you want to know your neighbors?",
    layout: "rows",
    options: [
      { value: "close", label: "A close-knit place where people stay", scale: { community: 1.6 } },
      { value: "friendly", label: "Friendly is enough" },
      { value: "private", label: "I mostly keep to myself", scale: { community: 0.6 } },
    ],
  },
};

// The order of each path. Steps that are not in QUESTIONS (home, money, winters, weights,
// picks) have their own screens in the wizard.
export const PATHS = {
  simple: ["who", "money", "nature", "winters", "picks"],
  more: ["who", "kidsFuture", "home", "money", "cost", "winters", "weather", "nature", "saturday",
    "safety", "hazard", "health", "work", "flights", "neighbors", "weights", "picks"],
};

// Every screen for these settings, starting with the choice of path.
export function stepsFor(s) {
  const path = PATHS[s.depth] || PATHS.simple;
  return ["depth", ...path.filter((id) => !QUESTIONS[id]?.when || QUESTIONS[id].when(s))];
}

// The chosen options, in path order, for the questions on the current path only: answers
// left over from a longer run are not applied to a shorter one.
export function chosenOptions(s) {
  const out = [];
  for (const id of stepsFor(s)) {
    const q = QUESTIONS[id], value = s.answers?.[id];
    const opt = q && q.options.find((o) => o.value === value);
    if (opt) out.push(opt);
  }
  return out;
}

// Settings saved before these questions existed (mode, kids, income, flights) become the
// matching answers, so "Redo setup" opens on what the visitor already said.
export function answersFromLegacy(s) {
  const a = { ...(s.answers || {}) };
  const kidsNow = s.kids === "now";
  if (!a.who && s.mode) a.who = s.mode === "couple" ? (kidsNow ? "family" : "couple") : (kidsNow ? "kids" : "solo");
  if (!a.kidsFuture && s.kids && !kidsNow) a.kidsFuture = s.kids === "planned" ? "yes" : "no";
  if (!a.work && s.income) a.work = { portable: "remote", partly: "partly", local: "local" }[s.income];
  if (!a.flights && s.flights) a.flights = s.flights;
  return Object.fromEntries(Object.entries(a).filter(([, v]) => v));
}
