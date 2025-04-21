// src/utils/termUtils.ts
export function formatTermLabel(termCode: string): string {
  if (termCode === 'CURRENT') return 'Current Term';
  // termCode is YYYYT T, e.g. "202320"
  const year = termCode.slice(0, 4);
  const suffix = termCode.slice(4);
  const nextYear = String(+year + 1);
  let name: string;
  switch (suffix) {
    case '10':
      name = 'Semester I';
      break;
    case '20':
      name = 'Semester II';
      break;
    case '40':
      name = 'Summer School';
      break;
    default:
      name = '';
  }
  return `${year}/${nextYear} ${name}`;
}
