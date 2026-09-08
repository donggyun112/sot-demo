export interface paths {
    "/api/v1/auth/google": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Google */
        post: operations["google_api_v1_auth_google_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/local": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Local */
        post: operations["local_api_v1_auth_local_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout All */
        post: operations["logout_all_api_v1_auth_logout_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invitations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Mine */
        get: operations["list_my_invitations"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invitations/redeem": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Redeem */
        post: operations["redeem_api_v1_invitations_redeem_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invitations/{invitation_id}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept */
        post: operations["accept_api_v1_invitations__invitation_id__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/invitations/{invitation_id}/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decline */
        post: operations["decline_api_v1_invitations__invitation_id__decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List For Actor */
        get: operations["list_for_actor_api_v1_workspaces_get"];
        put?: never;
        /** Create Workspace */
        post: operations["create_workspace_api_v1_workspaces_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_workspaces__workspace_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/agent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Run Agent */
        post: operations["run_agent_api_v1_workspaces__workspace_id__branches__branch_id__agent_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/attachments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Attach */
        post: operations["attach_api_v1_workspaces__workspace_id__branches__branch_id__attachments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/bundle-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preview */
        get: operations["preview_api_v1_workspaces__workspace_id__branches__branch_id__bundle_preview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/curation-ops": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Curate */
        post: operations["curate_api_v1_workspaces__workspace_id__branches__branch_id__curation_ops_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/branches/{branch_id}/turns": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Turns For Branch */
        get: operations["list_branch_turns"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/bundles/{bundle_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Cited */
        get: operations["read_cited_conversation"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List For Workspace */
        get: operations["list_workspace_documents"];
        put?: never;
        /** Create */
        post: operations["create_workspace_document"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_workspaces__workspace_id__documents__document_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Rename */
        patch: operations["rename_workspace_document"];
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/grounds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Grounds */
        get: operations["list_passage_grounds"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/proposals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Proposals For Document */
        get: operations["list_document_proposals"];
        put?: never;
        /** Create Proposal */
        post: operations["create_proposal_api_v1_workspaces__workspace_id__documents__document_id__proposals_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Revisions */
        get: operations["list_document_revisions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/revisions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Revision */
        get: operations["revision_api_v1_workspaces__workspace_id__documents__document_id__revisions__number__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/documents/{document_id}/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Sessions For Document */
        get: operations["list_document_sessions"];
        put?: never;
        /** Create */
        post: operations["create_api_v1_workspaces__workspace_id__documents__document_id__sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/invitations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Invitations */
        get: operations["list_invitations"];
        put?: never;
        /** Send Invitation */
        post: operations["send_invitation_api_v1_workspaces__workspace_id__invitations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/invitations/{invitation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Revoke */
        delete: operations["revoke_invitation"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Members */
        get: operations["list_workspace_members"];
        put?: never;
        /** Add */
        post: operations["add_api_v1_workspaces__workspace_id__members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/members/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current Member */
        get: operations["get_current_workspace_member"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Proposal */
        get: operations["read_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__get"];
        /** Revise Proposal */
        put: operations["revise_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Proposal */
        post: operations["decide_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__decisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/proposals/{proposal_id}/merge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Merge Proposal */
        post: operations["merge_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__merge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_api_v1_workspaces__workspace_id__sessions__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/branches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Branches For Session */
        get: operations["list_session_branches"];
        put?: never;
        /** Branch */
        post: operations["branch_api_v1_workspaces__workspace_id__sessions__session_id__branches_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/forks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Fork */
        post: operations["fork_api_v1_workspaces__workspace_id__sessions__session_id__forks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workspaces/{workspace_id}/sessions/{session_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Members Of Session */
        get: operations["list_session_members"];
        put?: never;
        /** Send Session */
        post: operations["send_session_api_v1_workspaces__workspace_id__sessions__session_id__members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/readyz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ready */
        get: operations["ready_readyz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AddWorkspaceMemberRequest */
        AddWorkspaceMemberRequest: {
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * ApprovalDecision
         * @enum {string}
         */
        ApprovalDecision: "approve" | "reject";
        /** ApprovalResponse */
        ApprovalResponse: {
            /**
             * Approver User Id
             * Format: uuid
             */
            approver_user_id: string;
            /**
             * Decided At
             * Format: date-time
             */
            decided_at: string;
            decision: components["schemas"]["ApprovalDecision"];
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            /** Version */
            version: number;
        };
        /** AttachmentRequest */
        AttachmentRequest: {
            /** Content */
            content: string;
            /** Expected Version */
            expected_version: number;
            /** Filename */
            filename: string;
        };
        /** AuthResponse */
        AuthResponse: {
            /** Access Token */
            access_token: string;
            /**
             * Token Type
             * @default bearer
             * @constant
             */
            token_type: "bearer";
            user: components["schemas"]["UserResponse"];
        };
        /** BranchMutationResponse */
        BranchMutationResponse: {
            /** Branch Version */
            branch_version: number;
            /**
             * Resource Id
             * Format: uuid
             */
            resource_id: string;
        };
        /** BranchResponse */
        BranchResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** BundleItemResponse */
        BundleItemResponse: {
            /** Content */
            content: string;
            /**
             * Provenance
             * @enum {string}
             */
            provenance: "copied" | "edited";
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant" | "tool";
            /** Source Ids */
            source_ids: string[];
        };
        /** CitationResponse */
        CitationResponse: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Bundle Item Position */
            bundle_item_position: number;
            /** Claim Anchor */
            claim_anchor: string;
        };
        /** CitedConversationResponse */
        CitedConversationResponse: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Items */
            items: components["schemas"]["BundleItemResponse"][];
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /** Title */
            title: string;
        };
        /** CreateDocumentRequest */
        CreateDocumentRequest: {
            /**
             * Content
             * @default
             */
            content: string;
            /** Title */
            title: string;
        };
        /** CreateProposalRequest */
        CreateProposalRequest: {
            /** Additional Approver Ids */
            additional_approver_ids?: string[];
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /** Edits */
            edits: components["schemas"]["DocumentEditRequest"][];
            /**
             * Source Session Id
             * Format: uuid
             */
            source_session_id: string;
        };
        /** CreateWorkspaceRequest */
        CreateWorkspaceRequest: {
            /** Name */
            name: string;
        };
        /** CreatedSessionResponse */
        CreatedSessionResponse: {
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
        };
        /** CurationRequest */
        CurationRequest: {
            /** Expected Version */
            expected_version: number;
            /** Operation */
            operation: components["schemas"]["DropTurnRequest"] | components["schemas"]["EditTurnRequest"] | components["schemas"]["JoinTurnsRequest"] | components["schemas"]["RestoreTurnRequest"];
        };
        /** CurrentWorkspaceMemberResponse */
        CurrentWorkspaceMemberResponse: {
            /** Permissions */
            permissions: components["schemas"]["Permission"][];
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** DecideProposalRequest */
        DecideProposalRequest: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "reject";
            /** Expected Version */
            expected_version: number;
        };
        /** DocumentEditRequest */
        DocumentEditRequest: {
            /**
             * Find
             * @default
             */
            find: string;
            /** Replace */
            replace: string;
        };
        /** DocumentEditResponse */
        DocumentEditResponse: {
            /** Find */
            find: string;
            /** Replace */
            replace: string;
        };
        /** DocumentResponse */
        DocumentResponse: {
            current_revision: components["schemas"]["RevisionResponse"];
            document: components["schemas"]["DocumentSummaryResponse"];
        };
        /** DocumentSummaryResponse */
        DocumentSummaryResponse: {
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** DropTurnRequest */
        DropTurnRequest: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "drop";
            /**
             * Turn Id
             * Format: uuid
             */
            turn_id: string;
        };
        /** EditTurnRequest */
        EditTurnRequest: {
            /** Content */
            content: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "edit";
            /**
             * Turn Id
             * Format: uuid
             */
            turn_id: string;
        };
        /** EmptySessionRequest */
        EmptySessionRequest: Record<string, never>;
        /** ForkSessionRequest */
        ForkSessionRequest: {
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** InvitationResponse */
        InvitationResponse: {
            /** Code */
            code?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Invitee Email */
            invitee_email: string;
            role: components["schemas"]["WorkspaceRole"];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** InviteRequest */
        InviteRequest: {
            /** Email */
            email: string;
            /**
             * Role
             * @default member
             * @enum {string}
             */
            role: "member" | "viewer";
        };
        /** JoinTurnsRequest */
        JoinTurnsRequest: {
            /** Content */
            content: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "join";
            /** Turn Ids */
            turn_ids: string[];
        };
        JsonValue: unknown;
        /** LoginRequest */
        LoginRequest: {
            /** Credential */
            credential: string;
        };
        /** MergeProposalRequest */
        MergeProposalRequest: {
            /** Expected Version */
            expected_version: number;
        };
        /** MergeProposalResponse */
        MergeProposalResponse: {
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            publication: components["schemas"]["PublicationResponse"] | null;
            status: components["schemas"]["ProposalStatus"];
            /** Version */
            version: number;
        };
        /**
         * MyInvitationResponse
         * @description What an invitee sees: who is asking, and to join what.
         */
        MyInvitationResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Inviter Display Name */
            inviter_display_name: string;
            role: components["schemas"]["WorkspaceRole"];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
            /** Workspace Name */
            workspace_name: string;
        };
        /** PassageGroundResponse */
        PassageGroundResponse: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Bundle Item Position */
            bundle_item_position: number;
            /** Claim Anchor */
            claim_anchor: string;
            /** Revision Number */
            revision_number: number;
            /** Session Id */
            session_id?: string | null;
            /** Tool Call Id */
            tool_call_id?: string | null;
        };
        /**
         * Permission
         * @enum {string}
         */
        Permission: "workspace.manage" | "document.create" | "document.read" | "document.publish" | "session.create" | "session.read" | "session.participate";
        /** ProposalResponse */
        ProposalResponse: {
            /** Approvals */
            approvals: components["schemas"]["ApprovalResponse"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            current_version: components["schemas"]["ProposalVersionResponse"];
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Source Session Id
             * Format: uuid
             */
            source_session_id: string;
            status: components["schemas"]["ProposalStatus"];
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * ProposalStatus
         * @enum {string}
         */
        ProposalStatus: "open" | "approved" | "rejected" | "stale" | "merged";
        /** ProposalVersionResponse */
        ProposalVersionResponse: {
            /** Additional Approver Ids */
            additional_approver_ids: string[];
            /**
             * Base Revision Id
             * Format: uuid
             */
            base_revision_id: string;
            /** Bundle Ids */
            bundle_ids: string[];
            /** Citations */
            citations: components["schemas"]["CitationResponse"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Edits */
            edits: components["schemas"]["DocumentEditResponse"][];
            /**
             * Proposal Id
             * Format: uuid
             */
            proposal_id: string;
            /** Required Approver Ids */
            required_approver_ids: string[];
            /** Version */
            version: number;
        };
        /** PublicationResponse */
        PublicationResponse: {
            document: components["schemas"]["PublishedDocumentResponse"];
            revision: components["schemas"]["PublishedRevisionResponse"];
        };
        /** PublishedDocumentResponse */
        PublishedDocumentResponse: {
            /**
             * Current Revision Id
             * Format: uuid
             */
            current_revision_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /** Version */
            version: number;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** PublishedRevisionResponse */
        PublishedRevisionResponse: {
            /** Citations */
            citations: components["schemas"]["CitationResponse"][];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Number */
            number: number;
            /** Proposal Id */
            proposal_id: string | null;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** RedeemRequest */
        RedeemRequest: {
            /** Code */
            code: string;
        };
        /** RenameDocumentRequest */
        RenameDocumentRequest: {
            /** Title */
            title: string;
        };
        /** RestoreTurnRequest */
        RestoreTurnRequest: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "restore";
            /**
             * Turn Id
             * Format: uuid
             */
            turn_id: string;
        };
        /** ReviseProposalRequest */
        ReviseProposalRequest: {
            /** Additional Approver Ids */
            additional_approver_ids?: string[] | null;
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /** Edits */
            edits: components["schemas"]["DocumentEditRequest"][];
            /** Expected Version */
            expected_version: number;
        };
        /** RevisionCitationResponse */
        RevisionCitationResponse: {
            /**
             * Bundle Id
             * Format: uuid
             */
            bundle_id: string;
            /** Bundle Item Position */
            bundle_item_position: number;
            /** Claim Anchor */
            claim_anchor: string;
        };
        /** RevisionResponse */
        RevisionResponse: {
            /** Citations */
            citations: components["schemas"]["RevisionCitationResponse"][];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Number */
            number: number;
            /** Proposal Id */
            proposal_id: string | null;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** RevisionSummaryResponse */
        RevisionSummaryResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Number */
            number: number;
            /** Proposal Id */
            proposal_id: string | null;
        };
        /** SendSessionRequest */
        SendSessionRequest: {
            /**
             * Role
             * @default editor
             * @enum {string}
             */
            role: "editor" | "viewer";
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** SessionMemberResponse */
        SessionMemberResponse: {
            role: components["schemas"]["SessionRole"];
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** SessionResponse */
        SessionResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Document Id */
            document_id: string | null;
            /** Forked From Branch Id */
            forked_from_branch_id?: string | null;
            /** Forked From Session Id */
            forked_from_session_id?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            status: components["schemas"]["SessionStatus"];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * SessionRole
         * @enum {string}
         */
        SessionRole: "owner" | "editor" | "viewer";
        /**
         * SessionStatus
         * @enum {string}
         */
        SessionStatus: "open" | "closed";
        /** TurnResponse */
        TurnResponse: {
            /**
             * Branch Id
             * Format: uuid
             */
            branch_id: string;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Ordinal */
            ordinal: number;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant" | "tool";
            /** Tool Call Id */
            tool_call_id?: string | null;
            /** Tool Kind */
            tool_kind?: ("call" | "return" | "retry") | null;
            tool_payload?: components["schemas"]["JsonValue"] | null;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** UserResponse */
        UserResponse: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /** WorkspaceMemberProfileResponse */
        WorkspaceMemberProfileResponse: {
            /** Display Name */
            display_name: string;
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** WorkspaceMemberResponse */
        WorkspaceMemberResponse: {
            role: components["schemas"]["WorkspaceRole"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** WorkspaceResponse */
        WorkspaceResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /**
         * WorkspaceRole
         * @enum {string}
         */
        WorkspaceRole: "owner" | "member" | "viewer";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    google_api_v1_auth_google_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    local_api_v1_auth_local_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthResponse"];
                };
            };
        };
    };
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    logout_all_api_v1_auth_logout_all_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthResponse"];
                };
            };
        };
    };
    list_my_invitations: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MyInvitationResponse"][];
                };
            };
        };
    };
    redeem_api_v1_invitations_redeem_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RedeemRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    accept_api_v1_invitations__invitation_id__accept_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                invitation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decline_api_v1_invitations__invitation_id__decline_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                invitation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    me_api_v1_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
        };
    };
    list_for_actor_api_v1_workspaces_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"][];
                };
            };
        };
    };
    create_workspace_api_v1_workspaces_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateWorkspaceRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_workspaces__workspace_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    run_agent_api_v1_workspaces__workspace_id__branches__branch_id__agent_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    attach_api_v1_workspaces__workspace_id__branches__branch_id__attachments_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AttachmentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchMutationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    preview_api_v1_workspaces__workspace_id__branches__branch_id__bundle_preview_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BundleItemResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    curate_api_v1_workspaces__workspace_id__branches__branch_id__curation_ops_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CurationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchMutationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_branch_turns: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                branch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TurnResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_cited_conversation: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                bundle_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CitedConversationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_workspace_documents: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentSummaryResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_workspace_document: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateDocumentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_workspaces__workspace_id__documents__document_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rename_workspace_document: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RenameDocumentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentSummaryResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_passage_grounds: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PassageGroundResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_document_proposals: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_proposal_api_v1_workspaces__workspace_id__documents__document_id__proposals_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_document_revisions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionSummaryResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revision_api_v1_workspaces__workspace_id__documents__document_id__revisions__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
                number: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RevisionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_document_sessions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_api_v1_workspaces__workspace_id__documents__document_id__sessions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EmptySessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedSessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_invitations: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvitationResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_invitation_api_v1_workspaces__workspace_id__invitations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InviteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvitationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revoke_invitation: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                invitation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_workspace_members: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberProfileResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    add_api_v1_workspaces__workspace_id__members_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddWorkspaceMemberRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_current_workspace_member: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrentWorkspaceMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    revise_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviseProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__decisions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecideProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    merge_proposal_api_v1_workspaces__workspace_id__proposals__proposal_id__merge_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                proposal_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MergeProposalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MergeProposalResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_api_v1_workspaces__workspace_id__sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_session_branches: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    branch_api_v1_workspaces__workspace_id__sessions__session_id__branches_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EmptySessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BranchResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    fork_api_v1_workspaces__workspace_id__sessions__session_id__forks_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ForkSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedSessionResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_session_members: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionMemberResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_session_api_v1_workspaces__workspace_id__sessions__session_id__members_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SendSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SessionMemberResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    ready_readyz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
}
