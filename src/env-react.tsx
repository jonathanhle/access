const defaultAccessTime = {
  '43200': '12 Hours',
  '432000': '5 Days',
  '1209600': 'Two Weeks',
  '2592000': '30 Days',
  '7776000': '90 Days',
  indefinite: 'Indefinite',
  custom: 'Custom',
} as const;

// Uses process.env.REACT_APP_ACCESS_TIME if defined, otherwise uses default
const AccessTime: Record<string, string> = process.env.REACT_APP_ACCESS_TIME
  ? JSON.parse(process.env.REACT_APP_ACCESS_TIME)
  : defaultAccessTime;

export {AccessTime};

// Default value for DEFAULT_ACCESS_TIME
const DEFAULT_ACCESS_TIME_DEFAULT = '1209600';

// Parse and export DEFAULT_ACCESS_TIME
export const DEFAULT_ACCESS_TIME: string = process.env.REACT_APP_DEFAULT_ACCESS_TIME
  ? process.env.REACT_APP_DEFAULT_ACCESS_TIME
  : DEFAULT_ACCESS_TIME_DEFAULT;
