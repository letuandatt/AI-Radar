import { expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ArticleBody, readingParagraphs } from '../knowledge/ArticleBody';

it('reflows long flat text without losing numbers, formulas or words', () => {
  const text = (
    'Coverage improves from 0.625 to 0.702. ' +
    'The model uses V_{strict} and α-nDCG@10. '
  ).repeat(15).trim();

  const paragraphs = readingParagraphs(text);

  expect(paragraphs.length).toBeGreaterThan(1);
  expect(paragraphs.join(' ')).toBe(text);

  const { container } = render(<ArticleBody text={text} />);
  expect(container.querySelectorAll('p').length).toBe(paragraphs.length);
});

it('renders explicit headings, paragraph boundaries and lists', () => {
  const text = [
    '## Abstract',
    'First paragraph.',
    'Second paragraph.',
    '• Finding one\n• Finding two',
  ].join('\n\n');

  const { container } = render(<ArticleBody text={text} />);

  expect(
    screen.getByRole('heading', { name: 'Abstract', level: 3 }),
  ).toBeVisible();
  expect(container.querySelectorAll('p')).toHaveLength(2);
  expect(screen.getAllByRole('listitem')).toHaveLength(2);
});

it('keeps source strings inert without creating HTML or fetching media', () => {
  const payload = '<img src="https://evil.example/pixel" onerror="alert(1)"> [link](javascript:alert(1))';
  const { container } = render(<ArticleBody text={payload} />);

  expect(screen.getByText(payload)).toBeVisible();
  expect(container.querySelector('img,script,iframe,a')).toBeNull();
});

it('preserves line breaks and supplies an empty state', () => {
  expect(readingParagraphs('Line one\nLine two')).toEqual([
    'Line one\nLine two',
  ]);

  render(<ArticleBody text="  " />);
  expect(screen.getByText('No article text available.')).toBeVisible();
});