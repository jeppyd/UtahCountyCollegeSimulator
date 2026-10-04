// The places you can go. "World" areas are the game; the research desk holds the deeper tools.
export type NavItem = { id: string; label: string; icon: string; hint: string; color?: string }
export const NAV: { group: string; label: string; items: NavItem[] }[] = [
  { group: 'world', label: 'The world', items: [
    { id: 'world', label: 'World', icon: 'globe', hint: 'What is happening right now: news, trends, lives to follow, the two worlds', color: '--s1' },
    { id: 'map', label: 'Map', icon: 'map', hint: 'Watch people move through Provo and Orem; color homes by anything', color: '--s3' },
    { id: 'people', label: 'People', icon: 'people', hint: 'Find and follow individual lives', color: '--s7' },
    { id: 'relationships', label: 'Relationships', icon: 'rings', hint: 'Couples, friendships and how people meet', color: '--s5' },
    { id: 'places', label: 'Places', icon: 'places', hint: 'Apartment complexes, wards, neighborhoods, schools', color: '--s4' },
    { id: 'events', label: 'Events', icon: 'events', hint: 'Everything that happens, and what caused it', color: '--s2' },
    { id: 'whatif', label: 'What-if', icon: 'butterfly', hint: 'Change the world and follow the butterfly effect', color: '--u-alt' },
    { id: 'explore', label: 'Explore', icon: 'explore', hint: 'Browse and chart every field the model tracks', color: '--s6' },
  ] },
  { group: 'research', label: 'Research desk', items: [
    { id: 'trends', label: 'Vital signs', icon: 'trend', hint: 'Population trends over time, in both worlds' },
    { id: 'flows', label: 'Flows over time', icon: 'network', hint: 'How people move between states (single → dating → married…)' },
    { id: 'crosstab', label: 'Cross-tabs', icon: 'desk', hint: 'How one thing varies by another, with statistics' },
    { id: 'causal', label: 'Cause & effect', icon: 'link', hint: 'The web of rules: what affects what' },
    { id: 'experiments', label: 'Experiments', icon: 'flask', hint: 'Monte Carlo runs and parameter sweeps' },
    { id: 'modelcheck', label: 'Model check', icon: 'spark', hint: 'How well the simulation matches real data' },
    { id: 'variables', label: 'Data dictionary', icon: 'book', hint: 'Definitions, sources and evidence for every field' },
    { id: 'mechanisms', label: 'Rules', icon: 'gear', hint: 'Every behavioral rule, its formula and evidence' },
    { id: 'about', label: 'Evidence & sources', icon: 'id', hint: 'Data sources, evidence levels, limitations' },
  ] },
  { group: 'help', label: '', items: [
    { id: 'guide', label: 'How it works', icon: 'book', hint: 'The field guide: how to play, and how the world works' },
  ] },
]
