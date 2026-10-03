// Deterministic, obviously synthetic display names — identical to ucsim/analysis/person.py.
const FIRST_F = ['Emma', 'Abigail', 'Hannah', 'Ellie', 'Olivia', 'Ava', 'Sarah', 'Rachel', 'Lydia', 'Eliza', 'Brooklyn', 'McKenna',
  'Kate', 'Lauren', 'Megan', 'Rebecca', 'Anna', 'Claire', 'Madison', 'Jenna', 'Sophie', 'Grace', 'Natalie', 'Camille']
const FIRST_M = ['Jacob', 'Ethan', 'Tyler', 'Spencer', 'Josh', 'Caleb', 'Sam', 'Nathan', 'Ben', 'Isaac', 'Tanner', 'Jared', 'Dallin',
  'Brigham', 'Carter', 'Logan', 'Michael', 'Daniel', 'Austin', 'Parker', 'Hunter', 'Mason', 'Luke', 'Andrew']
const LAST = ['Anderson', 'Christensen', 'Jensen', 'Larsen', 'Peterson', 'Smith', 'Johnson', 'Bowen', 'Hansen', 'Nielsen',
  'Taylor', 'Clark', 'Allen', 'Hall', 'Walker', 'Robinson', 'Thompson', 'Martinez', 'Nguyen', 'Garcia', 'Kimball',
  'Cannon', 'Richards', 'Snow', 'Lee', 'Pratt', 'Bennion', 'Ashby', 'Rasband', 'Wilkinson']

/** sexCode: 0 = F, 1 = M (registry order). */
export function nameOf(i: number, sexCode: number): string {
  const h = Number((BigInt(i) * 2654435761n) & 0xffffffffn)
  const first = (sexCode === 0 ? FIRST_F : FIRST_M)[h % 24]
  return `${first} ${LAST[Math.floor(h / 256) % LAST.length]}`
}
