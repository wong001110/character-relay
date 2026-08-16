import {
  useId,
  useState,
  type ChangeEventHandler,
  type HTMLAttributes,
  type ReactNode
} from "react";

import {
  Avatar,
  type AvatarStatus,
  Button,
  FormField,
  Input,
  PaperCard,
  Select,
  StickyLabel,
  StickyNote
} from "../ui";
import "./character-relay-ui.css";

function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface ProviderSelectProps {
  label?: ReactNode;
  hint?: ReactNode;
  value: string;
  options: SelectOption[];
  onChange: ChangeEventHandler<HTMLSelectElement>;
  disabled?: boolean;
  invalid?: boolean;
  className?: string;
}

export function ProviderSelect({
  label = "Provider",
  hint,
  value,
  options,
  onChange,
  disabled = false,
  invalid = false,
  className = ""
}: ProviderSelectProps) {
  const id = useId();
  return (
    <FormField className={cx("cr-domain-select-field", className)} label={label} hint={hint} htmlFor={id}>
      <Select id={id} value={value} onChange={onChange} disabled={disabled} invalid={invalid}>
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

export interface ModelSelectOption extends SelectOption {
  meta?: string;
}

export interface ModelSelectProps extends Omit<ProviderSelectProps, "options"> {
  options: ModelSelectOption[];
}

export function ModelSelect({
  label = "Model",
  hint,
  value,
  options,
  onChange,
  disabled = false,
  invalid = false,
  className = ""
}: ModelSelectProps) {
  const id = useId();
  return (
    <FormField className={cx("cr-domain-select-field", className)} label={label} hint={hint} htmlFor={id}>
      <Select id={id} value={value} onChange={onChange} disabled={disabled} invalid={invalid}>
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.meta ? `${option.label} · ${option.meta}` : option.label}
          </option>
        ))}
      </Select>
    </FormField>
  );
}

export interface ApiKeyFieldProps {
  label?: ReactNode;
  hint?: ReactNode;
  value?: string;
  defaultValue?: string;
  placeholder?: string;
  onChange?: ChangeEventHandler<HTMLInputElement>;
  disabled?: boolean;
  invalid?: boolean;
  className?: string;
  status?: ReactNode;
}

export function ApiKeyField({
  label = "API Key",
  hint,
  value,
  defaultValue,
  placeholder = "••••••••••••••••",
  onChange,
  disabled = false,
  invalid = false,
  className = "",
  status
}: ApiKeyFieldProps) {
  const id = useId();
  const [visible, setVisible] = useState(false);
  return (
    <FormField className={cx("cr-api-key-field", className)} label={label} hint={hint} htmlFor={id}>
      <div className="cr-api-key-field__control">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          value={value}
          defaultValue={defaultValue}
          onChange={onChange}
          placeholder={placeholder}
          disabled={disabled}
          invalid={invalid}
          autoComplete="off"
          spellCheck={false}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          aria-pressed={visible}
          onClick={() => setVisible((current) => !current)}
        >
          {visible ? "Hide" : "Show"}
        </Button>
      </div>
      {status && <div className="cr-api-key-field__status">{status}</div>}
    </FormField>
  );
}

export interface TopicNoteProps extends HTMLAttributes<HTMLDivElement> {
  topic: ReactNode;
  confidence?: number | null;
  participants?: ReactNode;
  status?: ReactNode;
}

export function TopicNote({
  className = "",
  topic,
  confidence,
  participants,
  status,
  children,
  ...props
}: TopicNoteProps) {
  return (
    <StickyNote className={cx("cr-topic-note", className)} variant="topic" pinned {...props}>
      <div className="cr-topic-note__heading">
        <StickyLabel variant="link">CURRENT TOPIC</StickyLabel>
        {status && <span className="cr-topic-note__status">{status}</span>}
      </div>
      <strong className="cr-topic-note__topic">{topic}</strong>
      {children && <div className="cr-topic-note__content">{children}</div>}
      {(typeof confidence === "number" || participants) && (
        <div className="cr-topic-note__meta">
          {typeof confidence === "number" && <span>confidence · {confidence.toFixed(2)}</span>}
          {participants && <span>{participants}</span>}
        </div>
      )}
    </StickyNote>
  );
}

export interface TemporaryRoleNoteProps extends Omit<HTMLAttributes<HTMLDivElement>, "role"> {
  role: ReactNode;
  note?: ReactNode;
}

export function TemporaryRoleNote({
  className = "",
  role,
  note = "temporary",
  ...props
}: TemporaryRoleNoteProps) {
  return (
    <StickyNote className={cx("cr-temporary-role-note", className)} variant="temporary" size="sm" {...props}>
      <StickyLabel variant="neutral">ROLE</StickyLabel>
      <strong>{role}</strong>
      {note && <small>{note}</small>}
    </StickyNote>
  );
}

export interface ParticipantCardProps extends HTMLAttributes<HTMLDivElement> {
  name: string;
  avatarSrc?: string;
  status?: AvatarStatus;
  subtitle?: ReactNode;
  labels?: ReactNode;
  runtimeState?: ReactNode;
  actions?: ReactNode;
}

export function ParticipantCard({
  className = "",
  name,
  avatarSrc,
  status = "idle",
  subtitle,
  labels,
  runtimeState,
  actions,
  ...props
}: ParticipantCardProps) {
  return (
    <PaperCard className={cx("cr-participant-card", className)} {...props}>
      <div className="cr-participant-card__identity">
        <Avatar name={name} src={avatarSrc} size="lg" status={status} />
        <div>
          <strong>{name}</strong>
          {subtitle && <p>{subtitle}</p>}
        </div>
      </div>
      {labels && <div className="cr-participant-card__labels">{labels}</div>}
      {runtimeState && (
        <StickyNote className="cr-participant-card__runtime" variant="temporary" size="sm">
          {runtimeState}
        </StickyNote>
      )}
      {actions && <div className="cr-participant-card__actions">{actions}</div>}
    </PaperCard>
  );
}