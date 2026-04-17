# React 19 `ref`를 props로 전달하는 패턴 가이드 (2026)

## 한 줄 요약

React 19에서는 **함수 컴포넌트가 `ref`를 “일반 prop처럼” 받을 수 있어** 많은 경우 `forwardRef` 래핑이 필요 없습니다. 다만 `forwardRef`가 “즉시 폐지/제거”된 것은 아니며, **향후 릴리스에서 deprecated 될 예정**입니다.

## 배경과 변경점

- **React < 19**: 함수 컴포넌트가 부모의 `ref`를 받으려면 `forwardRef`로 감싸고 두 번째 인자 `ref`로 전달받는 패턴이 일반적이었습니다.
- **React 19**: `ref`를 다른 prop처럼 컴포넌트의 파라미터로 직접 받아서, 내부 DOM/컴포넌트에 그대로 연결할 수 있습니다.

> 근거(공식): React 문서 `forwardRef` 페이지에서 “React 19에서는 `forwardRef`가 더 이상 필요하지 않다. 대신 `ref`를 prop으로 전달하라” 및 “`forwardRef`는 향후 릴리스에서 deprecated 될 예정”이라고 안내합니다.  
> - `https://react.dev/reference/react/forwardRef`
> - `https://react.dev/blog/2024/04/25/react-19#ref-as-a-prop`

## 코드 패턴

### React 18 스타일 (`forwardRef`)

```tsx
import React, { forwardRef } from "react";

type MyInputProps = {
  label: string;
} & React.ComponentPropsWithoutRef<"input">;

export const MyInput = forwardRef<HTMLInputElement, MyInputProps>(
  function MyInput({ label, ...props }, ref) {
    return (
      <label>
        {label}
        <input {...props} ref={ref} />
      </label>
    );
  }
);
```

### React 19 스타일 (`ref` as a prop)

```tsx
import React from "react";

type MyInputProps = {
  label: string;
  ref?: React.Ref<HTMLInputElement>;
} & React.ComponentPropsWithoutRef<"input">;

export function MyInput({ label, ref, ...props }: MyInputProps) {
  return (
    <label>
      {label}
      <input {...props} ref={ref} />
    </label>
  );
}
```

## 마이그레이션 체크리스트

- **`forwardRef` 제거 가능 여부**: 컴포넌트가 “ref를 받아서 하위 노드에 전달”만 한다면 React 19에서는 대부분 제거 가능합니다.
- **타입스크립트 타입**: `ref?: React.Ref<T>` (또는 `import type { Ref } from "react"` 후 `ref?: Ref<T>`)로 수신 타입을 단순화합니다.
- **호환성 주의**: React 18/17을 계속 지원해야 한다면, **`ref` as a prop 패턴만으로는 동작하지 않을 수 있어** 기존 `forwardRef`를 유지하거나 버전별 분기(빌드/패키지) 전략이 필요합니다.

## 자주 하는 실수/주의사항

- **`ref` 이름 충돌**: `ref`는 JSX에서 특별 취급되는 속성이었기 때문에, 팀 내 규칙(예: `innerRef`로 추상화)과 섞이면 혼동이 생길 수 있습니다. React 19 패턴을 채택한다면 “`ref`를 그대로 받는” 방식을 통일하는 편이 안전합니다.
- **`ref` 전달 누락**: (React 18 방식에서) `forwardRef`로 감싸놓고 `ref`를 실제 DOM/하위 컴포넌트에 연결하지 않으면 부모 ref는 계속 `null`입니다.

## 참고 링크 (SSOT)

- `https://react.dev/blog/2024/04/25/react-19`
- `https://react.dev/reference/react/forwardRef`

