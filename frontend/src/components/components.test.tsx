import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { Button, IconButton } from './Button.tsx';
import { Callout } from './Callout.tsx';
import { statusText } from './connectionStatus.ts';
import { DataTable } from './DataTable.tsx';
import { Dialog } from './Dialog.tsx';
import { KeyValueGrid } from './KeyValueGrid.tsx';
import { KpiTile } from './KpiTile.tsx';
import { Section } from './Section.tsx';
import { SegmentedControl } from './SegmentedControl.tsx';
import { Tag } from './Tag.tsx';
import { Toggle } from './Toggle.tsx';

describe('Toggle', () => {
  function Harness() {
    const [on, setOn] = useState(false);
    return <Toggle checked={on} onChange={setOn} label="Bundel meldingen" />;
  }

  it('is a switch that flips on click and keyboard', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const toggle = screen.getByRole('switch', { name: 'Bundel meldingen' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    await user.keyboard(' ');
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });
});

describe('SegmentedControl', () => {
  function Harness() {
    const [value, setValue] = useState('6 uur');
    return (
      <SegmentedControl
        label="Tijdbereik"
        value={value}
        onChange={setValue}
        options={['6 uur', '24 uur', '7 dagen'].map((v) => ({ value: v, label: v }))}
      />
    );
  }

  it('exposes a radio group with a single tab stop', () => {
    render(<Harness />);
    expect(screen.getByRole('radiogroup', { name: 'Tijdbereik' })).toBeInTheDocument();
    const radios = screen.getAllByRole('radio');
    expect(radios.map((r) => r.getAttribute('tabindex'))).toEqual(['0', '-1', '-1']);
    expect(screen.getByRole('radio', { name: '6 uur' })).toBeChecked();
  });

  it('moves selection and focus with arrow keys, Home and End', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.tab();
    expect(screen.getByRole('radio', { name: '6 uur' })).toHaveFocus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('radio', { name: '24 uur' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '24 uur' })).toHaveFocus();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    expect(screen.getByRole('radio', { name: '6 uur' })).toBeChecked();
    await user.keyboard('{ArrowLeft}');
    expect(screen.getByRole('radio', { name: '7 dagen' })).toBeChecked();
    await user.keyboard('{Home}');
    expect(screen.getByRole('radio', { name: '6 uur' })).toBeChecked();
    await user.keyboard('{End}');
    expect(screen.getByRole('radio', { name: '7 dagen' })).toHaveFocus();
  });

  it('selects on click', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('radio', { name: '24 uur' }));
    expect(screen.getByRole('radio', { name: '24 uur' })).toBeChecked();
  });
});

describe('Button', () => {
  it('defaults to type=button and forwards clicks', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Open advies</Button>);
    const button = screen.getByRole('button', { name: 'Open advies' });
    expect(button).toHaveAttribute('type', 'button');
    await user.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('gives icon buttons an accessible name and tooltip', () => {
    render(<IconButton aria-label="Sluiten" icon={<span />} />);
    expect(screen.getByRole('button', { name: 'Sluiten' })).toHaveAttribute('title', 'Sluiten');
  });
});

describe('DataTable', () => {
  const rows = [
    { id: '1', start: '06:05' },
    { id: '2', start: '06:15' },
  ];

  it('renders headers and rows, and selects rows by keyboard', async () => {
    const user = userEvent.setup();
    const onRowSelect = vi.fn();
    render(
      <DataTable
        caption="Alle cycli"
        columns={[{ key: 'start', header: 'Start', render: (r) => r.start }]}
        rows={rows}
        getRowKey={(r) => r.id}
        onRowSelect={onRowSelect}
        selectedKey="2"
      />,
    );
    expect(screen.getByRole('table', { name: 'Alle cycli' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Start' })).toBeInTheDocument();
    const [, first, second] = screen.getAllByRole('row');
    expect(second).toHaveAttribute('aria-selected', 'true');
    first?.focus();
    await user.keyboard('{Enter}');
    expect(onRowSelect).toHaveBeenCalledWith(rows[0]);
  });
});

describe('display components', () => {
  it('renders a KPI tile with explanation', () => {
    render(
      <KpiTile
        icon={<span />}
        tone="orange"
        label="Aanvoer"
        value="38,2 °C"
        sub="gemeten · 4 s"
        explain="Temperatuur van het water."
      />,
    );
    expect(screen.getByText('Aanvoer')).toBeInTheDocument();
    expect(screen.getByText('38,2 °C')).toBeInTheDocument();
    expect(screen.getByText('Temperatuur van het water.')).toBeInTheDocument();
  });

  it('renders a key-value grid as a definition list', () => {
    render(<KeyValueGrid items={[{ key: 'Reden', value: 'Omdat.' }]} />);
    expect(screen.getByRole('term')).toHaveTextContent('Reden');
    expect(screen.getByRole('definition')).toHaveTextContent('Omdat.');
  });

  it('labels a section by its heading', () => {
    render(
      <Section title="Bevindingen" action={<Button variant="ghost">Alles bekijken</Button>}>
        x
      </Section>,
    );
    expect(screen.getByRole('region', { name: 'Bevindingen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Alles bekijken' })).toBeInTheDocument();
  });

  it('renders tags and callouts', () => {
    render(
      <>
        <Tag tone="rose">Hoog</Tag>
        <Callout tone="error">Kon niet laden.</Callout>
      </>,
    );
    expect(screen.getByText('Hoog')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Kon niet laden.');
  });

  it('formats header status texts', () => {
    const t = new Date('2026-10-04T09:52:00Z');
    expect(statusText({ state: 'live', updatedAt: t })).toBe('Live · bijgewerkt 11:52');
    expect(statusText({ state: 'delayed', lastDataAt: t })).toBe(
      'Vertraagd · laatste gegevens 11:52',
    );
    expect(statusText({ state: 'importing', progress: 42 })).toBe('Historie importeren · 42 %');
  });
});

describe('Dialog', () => {
  function Harness({ dirty = false }: { dirty?: boolean }) {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button
          onClick={() => {
            setOpen(true);
          }}
        >
          Openen
        </Button>
        <Dialog
          open={open}
          onClose={() => {
            setOpen(false);
          }}
          title="Periode markeren"
          isDirty={dirty}
          footer={<Button>Vastleggen</Button>}
        >
          <input aria-label="Omschrijving" />
        </Dialog>
      </>
    );
  }

  it('focuses the first field, closes on Escape and restores focus', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const opener = screen.getByRole('button', { name: 'Openen' });
    await user.click(opener);
    const dialog = screen.getByRole('dialog', { name: 'Periode markeren' });
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(screen.getByRole('textbox', { name: 'Omschrijving' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(opener).toHaveFocus();
  });

  it('traps focus inside the dialog', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('button', { name: 'Openen' }));
    expect(screen.getByRole('textbox', { name: 'Omschrijving' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Vastleggen' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Sluiten' })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Vastleggen' })).toHaveFocus();
  });

  it('asks before discarding changes', async () => {
    const user = userEvent.setup();
    render(<Harness dirty />);
    await user.click(screen.getByRole('button', { name: 'Openen' }));
    await user.keyboard('{Escape}');
    expect(screen.getByText('Wijzigingen weggooien?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Weggooien' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
