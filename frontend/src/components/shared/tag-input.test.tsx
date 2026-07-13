/**
 * Unit tests for TagInput component (REQ-010).
 *
 * Covers: render pills, add on Enter, add on comma, remove on X-click,
 *         duplicate suppression, add on blur, remove-last on Backspace.
 *
 * req_id: REQ-010
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TagInput } from './tag-input';

describe('TagInput (REQ-010)', () => {
  it('renders existing tags as pills', () => {
    render(<TagInput tags={['ui', 'frontend']} onChange={() => {}} />);
    const pills = screen.getAllByTestId('tag-pill');
    expect(pills).toHaveLength(2);
    expect(screen.getByText('ui')).toBeInTheDocument();
    expect(screen.getByText('frontend')).toBeInTheDocument();
  });

  it('renders placeholder when no tags present', () => {
    render(
      <TagInput tags={[]} onChange={() => {}} placeholder="add a tag..." data-testid="ti" />
    );
    const input = screen.getByTestId('ti-input');
    expect(input).toHaveAttribute('placeholder', 'add a tag...');
  });

  it('adds tag on Enter key', () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: 'newtag' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith(['newtag']);
  });

  it('adds tag on comma key', () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: 'newtag' } });
    fireEvent.keyDown(input, { key: ',' });
    expect(onChange).toHaveBeenCalledWith(['newtag']);
  });

  it('clears the input after adding a tag', () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'newtag' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(input.value).toBe('');
  });

  it('removes tag on X-click', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['ui', 'backend']} onChange={onChange} />);
    const removeBtns = screen.getAllByTestId('tag-remove-btn');
    fireEvent.click(removeBtns[0]); // remove 'ui'
    expect(onChange).toHaveBeenCalledWith(['backend']);
  });

  it('removes second tag independently', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['ui', 'backend']} onChange={onChange} />);
    const removeBtns = screen.getAllByTestId('tag-remove-btn');
    fireEvent.click(removeBtns[1]); // remove 'backend'
    expect(onChange).toHaveBeenCalledWith(['ui']);
  });

  it('does not add duplicate tags', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['ui']} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: 'ui' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('trims whitespace before adding', () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: '  trimmed  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith(['trimmed']);
  });

  it('adds tag on blur with non-empty input', () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: 'blur-tag' } });
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith(['blur-tag']);
  });

  it('does NOT call onChange on blur when input is empty', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['existing']} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.blur(input);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('removes last tag on Backspace when input is empty', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['ui', 'frontend']} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input') as HTMLInputElement;
    // input is empty by default
    expect(input.value).toBe('');
    fireEvent.keyDown(input, { key: 'Backspace' });
    expect(onChange).toHaveBeenCalledWith(['ui']);
  });

  it('does NOT remove tag on Backspace when input has content', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['ui']} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: 'par' } });
    fireEvent.keyDown(input, { key: 'Backspace' });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('appends to existing tags on Enter', () => {
    const onChange = vi.fn();
    render(<TagInput tags={['existing']} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: 'second' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith(['existing', 'second']);
  });

  it('does not add empty-only tag', () => {
    const onChange = vi.fn();
    render(<TagInput tags={[]} onChange={onChange} data-testid="ti" />);
    const input = screen.getByTestId('ti-input');
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onChange).not.toHaveBeenCalled();
  });
});
