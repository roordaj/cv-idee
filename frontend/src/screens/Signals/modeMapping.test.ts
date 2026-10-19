import { modeTableText, parseModeTable } from './modeMapping';
it('maps Dutch labels to explicit canonical modes without guessing missing codes', () => {
  expect(parseModeTable('0 = stand-by\n3 = cv\n4 = tapwater\n6 = naloop\n1 = onbekend')).toEqual({
    table: { '0': 'standby', '3': 'ch', '4': 'dhw', '6': 'afterrun', '1': 'unknown' },
    error: null,
  });
  expect(parseModeTable('')).toEqual({ table: null, error: null });
  expect(modeTableText({ '3': 'ch', '4': 'dhw' })).toBe('3 = cv\n4 = tapwater');
});
it('rejects duplicate or unsupported meanings rather than defaulting', () => {
  expect(parseModeTable('3 = cv\n3 = tapwater').error).not.toBeNull();
  expect(parseModeTable('8 = storing').error).not.toBeNull();
  expect(parseModeTable('1 = cv = tapwater').error).not.toBeNull();
});
