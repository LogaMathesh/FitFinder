export const PREFERENCE_QUESTIONS = [
  {
    field: 'style_aesthetics',
    title: 'Which styles feel most like you?',
    description: 'Pick the looks you naturally reach for.',
    options: ['Casual', 'Streetwear', 'Ethnic', 'Formal', 'Minimal', 'Sporty', 'Vintage', 'Bohemian'],
  },
  {
    field: 'occasions',
    title: 'Where do you want outfit ideas for?',
    description: 'Choose the moments you dress for most.',
    options: ['Everyday', 'Work', 'Social events', 'Travel', 'Parties', 'Weddings', 'Festive occasions', 'Date nights'],
  },
  {
    field: 'preferred_colors',
    title: 'Which colors are you drawn to?',
    description: 'Think shades you enjoy wearing, not rules to follow.',
    options: ['Neutrals', 'Earth tones', 'Pastels', 'Bright colors', 'Monochrome', 'Jewel tones'],
  },
  {
    field: 'fit_priorities',
    title: 'What matters most in a good fit?',
    description: 'Choose what helps you feel at ease in your clothes.',
    options: ['Comfort', 'Relaxed fit', 'Tailored fit', 'Modest coverage', 'Easy layering'],
  },
  {
    field: 'outfit_goals',
    title: 'How would you like an outfit to feel?',
    description: 'Your own goals help us tailor suggestions to you.',
    options: ['Polished', 'Comfortable', 'Expressive', 'Understated', 'Stand out', 'Versatile'],
  },
];

export const EMPTY_PREFERENCES = Object.fromEntries(
  PREFERENCE_QUESTIONS.map(({ field }) => [field, []]),
);
