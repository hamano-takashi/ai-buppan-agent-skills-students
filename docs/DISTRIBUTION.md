# 講師向け 配布・更新手順

## 配布範囲

このリポジトリは非公開で運用します。受講生の招待は対象アカウントを確認してから管理者が行います。招待者・取得済みのZIPやクローンを含む情報管理が必要です。

個人アカウント所有の非公開リポジトリでは、共同作業者に読取専用権限を付与できず、書込権限が伴います。読取専用で招待する場合はOrganization所有のリポジトリでRead権限を使う運用を検討してください。招待前にこの点を確認します。招待解除は取得済みのローカルコピーを消去しません。

参照: [個人リポジトリの権限](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/permission-levels-for-a-personal-account-repository)、[Organizationの権限](https://docs.github.com/en/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/repository-roles-for-an-organization)（確認日: 2026-09-06）。

## 更新前

元の内部リポジトリをそのまま同期・pushしません。必要なスキルと参照資料だけを新しい候補へ移し、名前・数値・パス・接続先・権利・依存関係を確認します。教材の更新と受講生の個別データを分けます。

配布版には内部のGit履歴、認証、外部送信Hook、定期処理、案件ファイルを含めません。同梱されないツールを必須にしません。スキルを追加・削除したら SKILLS_INDEX.md も更新します。

## 検証と配布

Python 3.10以降で、リポジトリルートから次を実行します。追加のPythonパッケージは不要です。

```sh
python3 tools/test_validate_distribution.py
python3 tools/validate_distribution.py
```

Windowsでは python3 の代わりに py -3 を使える環境があります。検査が通らない理由を確認して修正します。manifestと一致しない変更は、内容の確認と人による機密・権利点検を終えてから次で一覧を更新します。

```sh
python3 tools/validate_distribution.py --write-manifest
python3 tools/validate_distribution.py
```

manifestの再作成は承認や機密保証の代わりではありません。検査後にファイルが変わったら再検査します。追加の秘密検査としてGitleaks等を利用する場合も、検査結果だけで機密なしと断定しません。

Gitのステージ対象と差分を確認し、配布ファイルだけをコミットします。タグや配布ZIPも同じファイル一覧で作ります。新しいリリースから受講生へ案内し、既存の個別資料を上書きする自動更新は行いません。

CI・公開サイト・通知・自動配信はこのリポジトリから設定しません。必要になった場合は追加の実行範囲として設計します。
